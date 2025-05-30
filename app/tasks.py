from app.celery_app import celery_app
from app.utils import get_supabase_client # Import the helper
# from app.models import Prompt, Result # If needed for type hinting or ORM-like use
import requests
from bs4 import BeautifulSoup
import openai
from dotenv import load_dotenv
load_dotenv()
import os
import json
from datetime import datetime
# Use the new OpenAI client for v1.x
from openai import OpenAI
from datetime import timedelta, timezone # Added timezone and timedelta

OPENAI_API_KEY_FROM_ENV = os.getenv("OPENAI_API_KEY") 
if OPENAI_API_KEY_FROM_ENV:
    client = OpenAI(api_key=OPENAI_API_KEY_FROM_ENV)
else:
    print("Warning: OPENAI_API_KEY not found. AI features will be limited.")


@celery_app.task
def information_retrieval_task(prompt_id: int, user_prompt: str):
    supabase = get_supabase_client() # This will raise ValueError if keys are default

    try:
        # 1. Update prompt status to 'processing_retrieval'
        update_status_payload = {"status": "processing_retrieval", "updated_at": datetime.now().isoformat()}
        supabase.table("prompts").update(update_status_payload).eq("id", prompt_id).execute()

        # 2. Perform information retrieval (simulated with OpenAI call for simplicity)
        raw_data_content = {}
        if OPENAI_API_KEY_FROM_ENV:
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that summarizes and extracts options."},
                        {"role": "user", "content": f"Gather key information and potential options related to the following query: {user_prompt}. Present it as a structured summary."}
                    ],
                    max_tokens=500
                )
                raw_data_content["llm_response"] = response.choices[0].message.content.strip()
            except Exception as e:
                print(f"OpenAI call failed for prompt_id {prompt_id}: {e}")
                raw_data_content["error"] = f"OpenAI call failed: {str(e)}"
                raw_data_content["placeholder_data"] = f"Simulated search data for '{user_prompt}'. Actual web search would go here."
        else:
            print(f"OpenAI API key not configured. Using placeholder data for prompt_id {prompt_id}.")
            raw_data_content["placeholder_data"] = f"Simulated search data for '{user_prompt}' (OpenAI API key not configured). Actual web search would go here."
        
        raw_data_json = json.dumps(raw_data_content)

        # 3. Store raw data in 'results' table
        insert_payload = {
            "prompt_id": prompt_id,
            "raw_data": raw_data_json,
            "created_at": datetime.now().isoformat()
            # 'processed_options' and 'summary' will be added by subsequent tasks
        }
        insert_response = supabase.table("results").insert(insert_payload).execute()
        
        # Check for errors during insert
        if hasattr(insert_response, 'error') and insert_response.error:
            raise Exception(f"Failed to insert results: {insert_response.error.message}")
        if not insert_response.data: # Supabase often returns data on success
             print(f"Warning: Insert response for prompt_id {prompt_id} had no data, but also no explicit error. Check Supabase logs.")
             # Depending on Supabase client version, this might not always indicate an error if error is None.


        # 4. Update prompt status to 'retrieval_complete'
        update_status_payload = {"status": "retrieval_complete", "updated_at": datetime.now().isoformat()}
        supabase.table("prompts").update(update_status_payload).eq("id", prompt_id).execute()
        
        return f"Information retrieval complete for prompt ID: {prompt_id}"

    except Exception as e:
        print(f"Error in information_retrieval_task for prompt_id {prompt_id}: {e}")
        # Update prompt status to 'retrieval_error'
        error_status_payload = {"status": "retrieval_error", "updated_at": datetime.now().isoformat()}
        try:
            supabase.table("prompts").update(error_status_payload).eq("id", prompt_id).execute()

            # Update scheduled_jobs status if this prompt came from a scheduled job
            prompt_details_response = supabase.table("prompts").select("source_job_id").eq("id", prompt_id).maybe_single().execute()
            if prompt_details_response.data and prompt_details_response.data.get("source_job_id"):
                source_job_id = prompt_details_response.data["source_job_id"]
                update_job_payload = {
                    "last_run_status": "failed_retrieval",
                    "updated_at": datetime.now(timezone.utc).isoformat() # Also update updated_at for the job
                }
                # Here, last_run_at was already set by scheduler_dispatcher or force_run task.
                # We are just updating the status of that run.
                supabase.table("scheduled_jobs").update(update_job_payload).eq("id", source_job_id).execute()
                print(f"Updated scheduled_job ID {source_job_id} to status 'failed_retrieval' due to error in prompt ID {prompt_id}.")
        except Exception as db_error:
            print(f"Failed to update prompt/job status to retrieval_error for prompt_id {prompt_id}: {db_error}")
        return f"Error during information retrieval for prompt ID: {prompt_id}. Error: {str(e)}"


@celery_app.task
def process_and_summarize_task(prompt_id: int, agent_id: int):
    supabase = get_supabase_client()

    # Fetch agent configuration
    agent_config_response = supabase.table("agents").select("summarization_prompt, role, content").eq("id", agent_id).maybe_single().execute()
    if agent_config_response.data is None:
        raise Exception(f"Agent configuration not found for agent_id: {agent_id}")

    agent_config = agent_config_response.data
    summarization_prompt_template = agent_config.get("summarization_prompt", "Default summarization prompt if not found")
    agent_role = agent_config.get("role", "system")
    agent_content_template = agent_config.get("content", "You are a helpful assistant that summarizes and extracts options.")

    # It's assumed openai.api_key is already set as in information_retrieval_task
    if not OPENAI_API_KEY_FROM_ENV:
        print("Warning: OPENAI_API_KEY not found. Summarization features will be limited.")
        # Update prompt status to indicate an error due to configuration
        error_status_payload = {"status": "summary_error_config", "updated_at": datetime.now().isoformat()}
        supabase.table("prompts").update(error_status_payload).eq("id", prompt_id).execute()
        return f"Summarization failed for prompt ID: {prompt_id} due to missing OpenAI API key."

    try:
        # 1. Update prompt status to 'processing_summary'
        update_status_payload = {"status": "processing_summary", "updated_at": datetime.now().isoformat()}
        supabase.table("prompts").update(update_status_payload).eq("id", prompt_id).execute()

        # 2. Fetch the raw_data from the 'results' table for the given prompt_id
        #    Assuming there's one main result entry per prompt_id that contains the raw_data.
        #    Fetch the most recent one if multiple could exist.
        result_response = supabase.table("results").select("id, raw_data").eq("prompt_id", prompt_id).order("created_at", desc=True).limit(1).execute()
        
        if not result_response.data:
            raise Exception(f"No raw data found in 'results' table for prompt_id: {prompt_id}")

        raw_result_entry = result_response.data[0]
        result_id = raw_result_entry["id"]
        raw_data_json = raw_result_entry["raw_data"]
        
        try:
            raw_data = json.loads(raw_data_json) # raw_data is stored as JSON string
            # Extract the actual content, e.g., from llm_response or placeholder_data
            content_to_summarize = raw_data.get("llm_response", raw_data.get("placeholder_data", ""))
            if not content_to_summarize:
                 raise Exception("Raw data content is empty or not in expected format.")
        except json.JSONDecodeError:
            # If raw_data wasn't a JSON string, treat it as plain text.
            content_to_summarize = raw_data_json


        # 3. Use AI to process and summarize the raw_data
        #    This is a placeholder for the actual processing and summarization logic.
        processed_options_str = "[]" # Default to empty JSON array string
        summary_text = "Default summary: No specific summary generated."

        try:
            user_message_content = summarization_prompt_template.replace("{content_to_summarize}", content_to_summarize)

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": agent_role, "content": agent_content_template},
                    {"role": "user", "content": user_message_content}
                ],
                max_tokens=700
            )
            ai_output_text = response.choices[0].message.content.strip()

            # Attempt to parse the AI output as JSON
            try:
                parsed_output = json.loads(ai_output_text)
                processed_options_list = parsed_output.get("options", [])
                processed_options_str = json.dumps(processed_options_list) # Store as JSON string
                summary_text = parsed_output.get("summary", "Summary could not be extracted.")
            except json.JSONDecodeError:
                print(f"Failed to parse LLM output as JSON for prompt_id {prompt_id}. Output: {ai_output_text}")
                # Fallback: use the raw output as summary, and indicate options weren't parsed
                summary_text = f"Summary (raw output, JSON parsing failed): {ai_output_text}"
                processed_options_str = json.dumps(["Could not parse options from AI output."])

        except Exception as e:
            print(f"OpenAI call for summarization failed for prompt_id {prompt_id}: {e}")
            summary_text = f"Error during AI summarization: {str(e)}"
            # Keep default empty options if AI call fails
            processed_options_str = json.dumps([f"Error during AI summarization: {str(e)}"])


        # 4. Store processed options and summary in the 'results' table (update existing row)
        update_payload = {
            "processed_options": processed_options_str,
            "summary": summary_text,
            "updated_at": datetime.now().isoformat()
        }
        supabase.table("results").update(update_payload).eq("id", result_id).execute()
        
        # 5. Update prompt status to 'completed'
        final_status_payload = {"status": "completed", "updated_at": datetime.now().isoformat()}
        supabase.table("prompts").update(final_status_payload).eq("id", prompt_id).execute()

        # Update scheduled_jobs status if this prompt came from a scheduled job
        try:
            prompt_details_response = supabase.table("prompts").select("source_job_id").eq("id", prompt_id).maybe_single().execute()
            if prompt_details_response.data and prompt_details_response.data.get("source_job_id"):
                source_job_id = prompt_details_response.data["source_job_id"]
                update_job_payload = {
                    "last_run_status": "completed_successfully",
                    # "updated_at" is already updated when last_run_at was set by dispatcher/force_run.
                    # Or, we can choose to update "updated_at" here as well to mark this specific change.
                    # For consistency with error handling below, let's update it.
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                supabase.table("scheduled_jobs").update(update_job_payload).eq("id", source_job_id).execute()
                print(f"Updated scheduled_job ID {source_job_id} to status 'completed_successfully' for prompt ID {prompt_id}.")
        except Exception as job_update_error:
            print(f"Failed to update scheduled_job status after successful summary for prompt ID {prompt_id}: {job_update_error}")

        return f"Processing and summarization complete for prompt ID: {prompt_id}"

    except Exception as e:
        print(f"Error in process_and_summarize_task for prompt_id {prompt_id}: {e}")
        error_status_payload = {"status": "summary_error", "updated_at": datetime.now().isoformat()}
        try:
            supabase.table("prompts").update(error_status_payload).eq("id", prompt_id).execute()

            # Update scheduled_jobs status if this prompt came from a scheduled job
            prompt_details_response = supabase.table("prompts").select("source_job_id").eq("id", prompt_id).maybe_single().execute()
            if prompt_details_response.data and prompt_details_response.data.get("source_job_id"):
                source_job_id = prompt_details_response.data["source_job_id"]
                update_job_payload = {
                    "last_run_status": "failed_summary", # More specific error status
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                supabase.table("scheduled_jobs").update(update_job_payload).eq("id", source_job_id).execute()
                print(f"Updated scheduled_job ID {source_job_id} to status 'failed_summary' due to error in prompt ID {prompt_id}.")
        except Exception as db_error:
            print(f"Failed to update prompt/job status to summary_error for prompt_id {prompt_id}: {db_error}")
        return f"Error during processing and summarization for prompt ID: {prompt_id}. Error: {str(e)}"


@celery_app.task
def mcp_task(prompt_id: int, urls: list[str]):
    supabase = get_supabase_client()

    if not OPENAI_API_KEY_FROM_ENV:
        print(f"Warning: OPENAI_API_KEY not found. MCP task for prompt_id {prompt_id} will be limited.")
        error_status_payload = {"status": "mcp_error_config", "updated_at": datetime.now().isoformat()}
        try:
            supabase.table("prompts").update(error_status_payload).eq("id", prompt_id).execute()
        except Exception as db_error:
            print(f"Failed to update prompt status to mcp_error_config for prompt_id {prompt_id}: {db_error}")
        return f"MCP task failed for prompt ID: {prompt_id} due to missing OpenAI API key."

    try:
        update_status_payload = {"status": "processing_mcp", "updated_at": datetime.now().isoformat()}
        supabase.table("prompts").update(update_status_payload).eq("id", prompt_id).execute()
    except Exception as db_error:
        print(f"Failed to update prompt status to processing_mcp for prompt_id {prompt_id}: {db_error}")
        # Optionally re-raise or handle if this is critical before proceeding

    try:
        # TODO: Implement URL fetching and content extraction
        print(f"MCP task received for prompt_id: {prompt_id} with URLs: {urls}") # Temporary print

        all_extracted_text = []
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

        for url in urls:
            try:
                print(f"Processing URL: {url}")
                if "youtube.com/" in url or "youtu.be/" in url:
                    all_extracted_text.append(f"Content from YouTube URL ({url}): Transcription not yet implemented.")
                    # TODO: In a future iteration, integrate YouTube transcription service here.
                    continue

                response = requests.get(url, headers=headers, timeout=10) # 10 second timeout
                response.raise_for_status() # Raises an HTTPError for bad responses (4XX or 5XX)

                # Use BeautifulSoup to parse HTML and extract text
                soup = BeautifulSoup(response.content, 'html.parser')

                # Remove script and style elements
                for script_or_style in soup(["script", "style"]):
                    script_or_style.decompose()

                # Get text
                text = soup.get_text(separator='\n', strip=True)
                all_extracted_text.append(text)
                print(f"Successfully extracted text from {url}")

            except requests.exceptions.RequestException as e:
                print(f"Error fetching URL {url}: {e}")
                all_extracted_text.append(f"[Error fetching content from {url}: {str(e)}]")
            except Exception as e:
                print(f"Error processing URL {url} with BeautifulSoup: {e}")
                all_extracted_text.append(f"[Error processing content from {url}: {str(e)}]")

        combined_text = "\n\n--- Next Source ---\n\n".join(all_extracted_text)

        # Make combined_text available for the next step (summarization)
        # For now, we can just print it or store it in a variable that the summarization placeholder will use.
        print(f"Combined text length: {len(combined_text)}")
        if not combined_text.strip():
            print("No text could be extracted from the provided URLs.")
            # Potentially update status to an error or a specific "no_content" status here
            # For now, let the task proceed, OpenAI call might handle empty input gracefully or error out.

        mcp_summary_text = "Default MCP summary: No specific summary generated."
        # Placeholder for structured results like key quotes
        # key_quotes = []

        if not combined_text.strip():
            mcp_summary_text = "No content was extracted from the provided URLs to summarize."
        elif not OPENAI_API_KEY_FROM_ENV: # Should have been caught earlier, but as a safeguard
            mcp_summary_text = "OpenAI API key not configured. Cannot generate MCP summary."
        else:
            try:
                # Truncate combined_text to avoid exceeding token limits (e.g., ~12000 chars for a 4k token model context)
                # This is a simple approach. A more robust solution might involve chunking.
                # Average token length is ~4 chars. 3000 tokens * 4 chars/token = 12000 chars for user content.
                max_chars = 12000
                if len(combined_text) > max_chars:
                    print(f"Warning: Combined text length ({len(combined_text)}) exceeds max_chars ({max_chars}). Truncating.")
                    combined_text = combined_text[:max_chars]

                # Define the prompt for the LLM
                # The user wants a "resume" and "Key Quotes"
                # For now, we will aim for a textual summary that includes key quotes.
                # A more advanced version might ask for JSON.
                mcp_prompt = (
                    "You are an expert research assistant. Based on the following text compiled from various web sources, "
                    "please create a concise resume or summary. Your summary should highlight the most important information "
                    "and explicitly include several Key Quotes from the text that capture essential points or statements. "
                    "Structure the output clearly.\n\n"
                    "Source Text:\n"
                    "---------------------\n"
                    f"{combined_text}\n"
                    "---------------------\n\n"
                    "Resume/Summary with Key Quotes:"
                )

                response = client.chat.completions.create(
                    model="gpt-3.5-turbo", # Or a model suitable for longer contexts if available and configured
                    messages=[
                        {"role": "system", "content": "You are an AI assistant skilled in summarizing text and extracting key information and quotes."},
                        {"role": "user", "content": mcp_prompt}
                    ],
                    max_tokens=1000  # Adjust as needed, allowing for a decent-sized summary
                )
                mcp_summary_text = response.choices[0].message.content.strip()
                # TODO: Implement parsing of key quotes if a structured response is attempted later.

            except Exception as e:
                print(f"OpenAI call for MCP summarization failed for prompt_id {prompt_id}: {e}")
                mcp_summary_text = f"Error during AI summarization for MCP task: {str(e)}"

        # Ensure mcp_summary_text is available for the next step (storing results)
        # For now, print it:
        print(f"MCP Summary: {mcp_summary_text}")

        try:
            # Find the relevant result_id for the given prompt_id
            # Assuming we update the most recent result associated with the prompt_id
            result_response = supabase.table("results").select("id").eq("prompt_id", prompt_id).order("created_at", desc=True).limit(1).execute()

            if not result_response.data:
                raise Exception(f"No result entry found in 'results' table for prompt_id: {prompt_id} to store MCP data.")

            result_id_to_update = result_response.data[0]['id']

            update_payload = {
                "mcp_data": mcp_summary_text, # IMPORTANT: The 'results' table requires a new TEXT column named 'mcp_data' for this to work.
                "updated_at": datetime.now().isoformat()
            }

            update_response = supabase.table("results").update(update_payload).eq("id", result_id_to_update).execute()

            if hasattr(update_response, 'error') and update_response.error:
                raise Exception(f"Failed to store MCP results: {update_response.error.message}")

            print(f"MCP results stored successfully for result_id: {result_id_to_update}")

        except Exception as e:
            print(f"Error storing MCP results for prompt_id {prompt_id}: {e}")
            # Update prompt status to mcp_error_storage if not already in an error state
            error_status_payload = {"status": "mcp_error_storage", "updated_at": datetime.now().isoformat()}
            supabase.table("prompts").update(error_status_payload).eq("id", prompt_id).execute()
            # Allow the main exception handler to return the error message for the task
            raise # Re-raise the exception to be caught by the main task error handler

        final_status_payload = {"status": "mcp_complete", "updated_at": datetime.now().isoformat()}
        supabase.table("prompts").update(final_status_payload).eq("id", prompt_id).execute()
        return f"MCP task completed for prompt ID: {prompt_id}"

    except Exception as e:
        print(f"Error in mcp_task for prompt_id {prompt_id}: {e}")
        # The error status might have been set to 'mcp_error_storage' already if storage failed.
        # If it's another error, or if it didn't reach storage error handling, set to 'mcp_error'.
        # To avoid overwriting a more specific error, could check current status or let this be general.
        # For simplicity here, we'll set it to 'mcp_error' if it reaches this general handler.
        # A more sophisticated error handling could preserve specific error states.
        current_status_response = supabase.table("prompts").select("status").eq("id", prompt_id).single().execute()
        if current_status_response.data and current_status_response.data.get("status") not in ["mcp_error_storage", "mcp_error_config"]:
            error_status_payload = {"status": "mcp_error", "updated_at": datetime.now().isoformat()}
            try:
                supabase.table("prompts").update(error_status_payload).eq("id", prompt_id).execute()
            except Exception as db_error:
                print(f"Failed to update prompt status to mcp_error for prompt_id {prompt_id}: {db_error}")
        return f"Error during MCP task for prompt ID: {prompt_id}. Error: {str(e)}"


# Helper function to calculate the next run time
def calculate_next_run(current_next_run_at: datetime, iteration_type: str) -> datetime:
    """
    Calculates the next run time based on the iteration type.
    """
    now = datetime.now(timezone.utc)
    if not current_next_run_at: # Should not happen if job is well-formed
        current_next_run_at = now

    # If current_next_run_at is in the past, ensure the next run is in the future from now.
    # This handles jobs that might have been missed.
    if current_next_run_at < now:
        current_next_run_at = now

    if iteration_type == "hourly":
        return current_next_run_at + timedelta(hours=1)
    elif iteration_type == "daily":
        return current_next_run_at + timedelta(days=1)
    elif iteration_type.startswith("weekly_"): # e.g., weekly_monday
        # Simplistic approach: add 7 days. UI ensures initial next_run_at is correct.
        # A more robust solution would find the specific next day of the week.
        return current_next_run_at + timedelta(days=7)
    else:
        # Default or unknown: schedule for 1 day later to avoid rapid re-runs
        # Log a warning as well
        print(f"Warning: Unknown iteration_type '{iteration_type}'. Defaulting to 1 day.")
        return current_next_run_at + timedelta(days=1)

@celery_app.task
def scheduler_dispatcher_task():
    """
    Checks for scheduled jobs that are due, creates prompts for them,
    and schedules their next run.
    """
    supabase = get_supabase_client()
    now_utc = datetime.now(timezone.utc)
    print(f"Scheduler dispatcher task running at {now_utc.isoformat()}")

    try:
        # Query for active jobs that are due
        # Ensure next_run_at is compared with current UTC time
        scheduled_jobs_response = supabase.table("scheduled_jobs").select("*").eq("status", "active").lte("next_run_at", now_utc.isoformat()).execute()

        if hasattr(scheduled_jobs_response, 'error') and scheduled_jobs_response.error:
            print(f"Error fetching scheduled jobs: {scheduled_jobs_response.error}")
            return "Error fetching scheduled jobs"

        if not scheduled_jobs_response.data:
            print("No scheduled jobs due at this time.")
            return "No scheduled jobs due."

        for job in scheduled_jobs_response.data:
            print(f"Processing scheduled job ID: {job['id']} - {job['prompt_text'][:50]}...")

            try:
                # 1. Create a new entry in the prompts table
                new_prompt_payload = {
                    "user_prompt": job['prompt_text'],
                    "status": "pending_retrieval", # Initial status
                    "created_at": now_utc.isoformat(),
                    "source_job_id": job['id'], # Link back to the scheduled job
                    "agent_id": job.get("agent_id") # Ensure agent_id is carried over if present
                }
                new_prompt_response = supabase.table("prompts").insert(new_prompt_payload).execute()

                if hasattr(new_prompt_response, 'error') and new_prompt_response.error:
                    print(f"Error creating prompt for job ID {job['id']}: {new_prompt_response.error}")
                    # Update job with error status for this run
                    supabase.table("scheduled_jobs").update({
                        "last_run_status": f"failure_prompt_creation: {new_prompt_response.error.message}",
                        "last_run_at": now_utc.isoformat()
                    }).eq("id", job['id']).execute()
                    continue # Move to the next job

                if not new_prompt_response.data:
                    print(f"Prompt creation for job ID {job['id']} returned no data but no error. Skipping.")
                    # Update job with error status for this run
                    supabase.table("scheduled_jobs").update({
                        "last_run_status": "failure_prompt_creation: no data returned",
                        "last_run_at": now_utc.isoformat()
                    }).eq("id", job['id']).execute()
                    continue

                new_prompt_id = new_prompt_response.data[0]['id']
                print(f"Successfully created prompt ID: {new_prompt_id} for job ID: {job['id']}")

                # 2. Call information_retrieval_task
                # Ensure all necessary arguments for information_retrieval_task are passed.
                # Based on its definition: information_retrieval_task(prompt_id: int, user_prompt: str)
                information_retrieval_task.delay(prompt_id=new_prompt_id, user_prompt=job['prompt_text'])
                print(f"Dispatched information_retrieval_task for prompt ID: {new_prompt_id}")

                # 3. Calculate next run time
                # Ensure job['next_run_at'] is parsed to datetime if it's a string
                current_job_next_run_at_str = job['next_run_at']
                current_job_next_run_at_dt = datetime.fromisoformat(current_job_next_run_at_str.replace('Z', '+00:00')) if isinstance(current_job_next_run_at_str, str) else current_job_next_run_at_str

                if not isinstance(current_job_next_run_at_dt, datetime):
                    # Fallback if parsing fails or it's not already a datetime object
                    print(f"Warning: Could not parse job['next_run_at'] ({current_job_next_run_at_str}) as datetime. Using current time as base for next run calculation.")
                    current_job_next_run_at_dt = now_utc

                new_next_run_at = calculate_next_run(current_job_next_run_at_dt, job['iteration_type'])

                # 4. Update the scheduled_jobs entry
                update_job_payload = {
                    "last_run_at": now_utc.isoformat(),
                    "next_run_at": new_next_run_at.isoformat(),
                    "last_prompt_id": new_prompt_id,
                    "last_run_status": "triggered_retrieval"
                }
                update_job_response = supabase.table("scheduled_jobs").update(update_job_payload).eq("id", job['id']).execute()

                if hasattr(update_job_response, 'error') and update_job_response.error:
                    print(f"Error updating scheduled job ID {job['id']}: {update_job_response.error}")
                    # This error is less critical as the prompt is already triggered, but should be logged.
                else:
                    print(f"Successfully updated scheduled job ID: {job['id']}. Next run at: {new_next_run_at.isoformat()}")

            except Exception as e:
                print(f"An unexpected error occurred while processing job ID {job['id']}: {e}")
                # Update job with error status for this run
                try:
                    supabase.table("scheduled_jobs").update({
                        "last_run_status": f"failure_processing: {str(e)}",
                        "last_run_at": now_utc.isoformat()
                    }).eq("id", job['id']).execute()
                except Exception as db_error:
                    print(f"Failed to update job status after unexpected error for job ID {job['id']}: {db_error}")
                # Continue to the next job

        return f"Scheduler dispatcher task completed. Processed {len(scheduled_jobs_response.data)} jobs."

    except Exception as e:
        print(f"A critical error occurred in scheduler_dispatcher_task: {e}")
        # This is an error in the task itself, not specific to a job
        return f"Critical error in scheduler_dispatcher_task: {str(e)}"


@celery_app.task
def force_run_scheduled_job_task(schedule_id: int):
    """
    Manually triggers a specific scheduled job to run immediately.
    This does not change its next_run_at time.
    """
    supabase = get_supabase_client()
    now_utc = datetime.now(timezone.utc)
    print(f"Force run requested for scheduled job ID: {schedule_id} at {now_utc.isoformat()}")

    try:
        # Fetch the job details
        job_response = supabase.table("scheduled_jobs").select("*").eq("id", schedule_id).single().execute()

        if hasattr(job_response, 'error') and job_response.error:
            print(f"Error fetching job ID {schedule_id} for force run: {job_response.error}")
            return f"Error fetching job details for ID {schedule_id}"

        if not job_response.data:
            print(f"Scheduled job ID {schedule_id} not found for force run.")
            return f"Scheduled job ID {schedule_id} not found."

        job = job_response.data
        print(f"Job details fetched for force run: {job['job_name']}")

        # Create a new prompt
        new_prompt_payload = {
            "user_prompt": job['prompt_text'],
            "status": "pending_retrieval", # Initial status for a new prompt
            "created_at": now_utc.isoformat(),
            "source_job_id": job['id'],
            "agent_id": job.get("agent_id") # Carry over agent_id
        }
        new_prompt_response = supabase.table("prompts").insert(new_prompt_payload).execute()

        if hasattr(new_prompt_response, 'error') and new_prompt_response.error:
            print(f"Error creating prompt for force-run job ID {job['id']}: {new_prompt_response.error}")
            # Update the job's last_run_status to indicate this failure
            supabase.table("scheduled_jobs").update({
                "last_run_status": f"manual_trigger_failure_prompt: {new_prompt_response.error.message}",
                "last_run_at": now_utc.isoformat() # Also update last_run_at
            }).eq("id", schedule_id).execute()
            return f"Failed to create prompt for force-run job ID {schedule_id}"

        if not new_prompt_response.data:
            print(f"Prompt creation for force-run job ID {job['id']} returned no data but no error.")
            supabase.table("scheduled_jobs").update({
                "last_run_status": "manual_trigger_failure_prompt: no data returned",
                "last_run_at": now_utc.isoformat()
            }).eq("id", schedule_id).execute()
            return f"Failed to create prompt (no data) for force-run job ID {schedule_id}"

        new_prompt_id = new_prompt_response.data[0]['id']
        print(f"Successfully created prompt ID: {new_prompt_id} for force-run job ID: {job['id']}")

        # Dispatch the information retrieval task
        information_retrieval_task.delay(prompt_id=new_prompt_id, user_prompt=job['prompt_text'])
        print(f"Dispatched information_retrieval_task for prompt ID: {new_prompt_id} (force run)")

        # Update the scheduled job's last run info
        update_job_payload = {
            "last_run_at": now_utc.isoformat(),
            "last_prompt_id": new_prompt_id,
            "last_run_status": "manual_trigger_retrieval_ok"
        }
        update_job_response = supabase.table("scheduled_jobs").update(update_job_payload).eq("id", schedule_id).execute()

        if hasattr(update_job_response, 'error') and update_job_response.error:
            print(f"Error updating scheduled job ID {schedule_id} after force run: {update_job_response.error}")
            # This is not critical enough to fail the task, but should be logged.

        return f"Force run for job ID {schedule_id} completed. Prompt ID {new_prompt_id} created and dispatched."

    except Exception as e:
        print(f"An unexpected error occurred during force_run_scheduled_job_task for ID {schedule_id}: {e}")
        # Attempt to update the job status to reflect the error if possible
        try:
            supabase.table("scheduled_jobs").update({
                "last_run_status": f"manual_trigger_failure_unexpected: {str(e)}",
                "last_run_at": now_utc.isoformat()
            }).eq("id", schedule_id).execute()
        except Exception as db_error:
            print(f"Failed to update job status after unexpected error for force-run job ID {schedule_id}: {db_error}")
        return f"Unexpected error during force run for job ID {schedule_id}: {str(e)}"
