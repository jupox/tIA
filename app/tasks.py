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
        except Exception as db_error:
            print(f"Failed to update prompt status to retrieval_error for prompt_id {prompt_id}: {db_error}")
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

        return f"Processing and summarization complete for prompt ID: {prompt_id}"

    except Exception as e:
        print(f"Error in process_and_summarize_task for prompt_id {prompt_id}: {e}")
        error_status_payload = {"status": "summary_error", "updated_at": datetime.now().isoformat()}
        try:
            supabase.table("prompts").update(error_status_payload).eq("id", prompt_id).execute()
        except Exception as db_error:
            print(f"Failed to update prompt status to summary_error for prompt_id {prompt_id}: {db_error}")
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
