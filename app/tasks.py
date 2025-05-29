from app.celery_app import celery_app
from app.utils import get_supabase_client # Import the helper
# from app.models import Prompt, Result # If needed for type hinting or ORM-like use
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
def process_and_summarize_task(prompt_id: int):
    supabase = get_supabase_client()
    # It's assumed openai.api_key is already set as in information_retrieval_task
    if not openai.api_key:
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
            summarization_prompt = (
                f"Analyze the following text and extract key options or points, and provide a concise summary.\n"
                f"Text to analyze: \"{content_to_summarize}\"\n\n"
                f"Respond in a JSON format with two keys: 'options' (a list of strings) and 'summary' (a string)."
            )
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes and extracts options."},
                    {"role": "user", "content": summarization_prompt}
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
