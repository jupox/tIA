from app.states.toast import ToastState
import reflex as rx
from .utils import get_supabase_client
from .models import Prompt, Result # Assuming models.py might be used for Pydantic types if needed by Reflex state
from .tasks import calculate_next_run, information_retrieval_task, process_and_summarize_task, force_run_scheduled_job_task # Import Celery tasks
from datetime import datetime, timedelta, timezone # Added timedelta, timezone
import json # For parsing processed_options

class State(rx.State):
    prompt: str = ""
    current_prompt_id: int | None = None
    is_loading: bool = False
    
    # For displaying results
    result: str = "Output will appear here." # General status messages
    processed_options: list[str] = []
    summary: str = ""
    error_message: str = ""

    # Scheduler State Variables
    scheduled_jobs: list[dict] = []
    show_scheduler_modal: bool = False
    scheduler_modal_title: str = "Create Scheduled Job"
    current_schedule_id: int | None = None
    scheduler_job_name: str = ""
    scheduler_prompt_text: str = ""
    scheduler_iteration_type: str = "daily" # Default value
    scheduler_agent_id: str = "" # Store as string for input
    scheduler_status: str = "active" # Default value
    scheduler_error_message: str = ""
    scheduler_is_loading: bool = False
    iteration_options: list[dict] = [
        {"label": "Every Hour", "value": "hourly"},
        {"label": "Every Day (at 00:00 UTC next occurrence)", "value": "daily"},
        {"label": "Weekly - Monday (at 00:00 UTC next occurrence)", "value": "weekly_monday"},
        {"label": "Weekly - Tuesday (at 00:00 UTC next occurrence)", "value": "weekly_tuesday"},
        {"label": "Weekly - Wednesday (at 00:00 UTC next occurrence)", "value": "weekly_wednesday"},
        {"label": "Weekly - Thursday (at 00:00 UTC next occurrence)", "value": "weekly_thursday"},
        {"label": "Weekly - Friday (at 00:00 UTC next occurrence)", "value": "weekly_friday"},
        {"label": "Weekly - Saturday (at 00:00 UTC next occurrence)", "value": "weekly_saturday"},
        {"label": "Weekly - Sunday (at 00:00 UTC next occurrence)", "value": "weekly_sunday"},
    ]
    iteration_options_values: list[str] = [opt['value'] for opt in iteration_options]

    prompts: list[dict] = []  # Store all prompts
    toast_message: str = ""  # Message for toast notifications

    archived_prompts: list[dict] = []  # Store all archived prompts
    show_archived_modal: bool = False  # Control visibility of the archived prompts modal
    archived_error_message: str = ""  # Error message for archived prompts actions

    show_last_run_modal: bool = False
    last_run_details: str = ""
    last_run_error_message: str = ""

    @rx.event
    def open_scheduler_modal(self, schedule_data: dict | None = None):
        """Open the scheduler modal with data for editing or a blank form for creating."""
        self.scheduler_error_message = ""  # Clear previous errors
        if schedule_data:
            self.current_schedule_id = schedule_data['id']
            self.scheduler_job_name = schedule_data.get('job_name', '')
            self.scheduler_prompt_text = schedule_data.get('prompt_text', '')
            self.scheduler_iteration_type = schedule_data.get('iteration_type', 'daily')
            self.scheduler_agent_id = str(schedule_data.get('agent_id', '')) if schedule_data.get('agent_id') is not None else ""
            self.scheduler_status = schedule_data.get('status', 'active')
            self.scheduler_modal_title = "Edit Scheduled Job"
        else:
            self.current_schedule_id = None
            self.scheduler_job_name = ""
            self.scheduler_prompt_text = ""
            self.scheduler_iteration_type = "daily"
            self.scheduler_agent_id = ""
            self.scheduler_status = "active"
            self.scheduler_modal_title = "Create Scheduled Job"
        self.show_scheduler_modal = True

    @rx.event
    def set_scheduler_iteration_type(self, iteration_type: str):
        """Set the iteration type for the scheduler."""
        if iteration_type in self.iteration_options_values:
            self.scheduler_iteration_type = iteration_type
        else:
            self.scheduler_error_message = f"Invalid iteration type: {iteration_type}"

    @rx.event
    def set_scheduler_job_name(self, job_name: str):
        """Set the job name for the scheduler."""
        self.scheduler_job_name = job_name.strip()

    @rx.event
    def set_scheduler_prompt_text(self, prompt_text: str):
        """Set the prompt text for the scheduler."""
        self.scheduler_prompt_text = prompt_text.strip()

    @rx.event
    def set_scheduler_agent_id(self, agent_id: str):
        """Set the agent ID for the scheduler."""
        self.scheduler_agent_id = agent_id.strip()

    @rx.event
    def set_scheduler_status(self, status: str):
        """Set the status for the scheduler."""
        if status in ["active", "paused"]:
            self.scheduler_status = status
        else:
            self.scheduler_error_message = f"Invalid status: {status}"

    @rx.event
    def set_show_scheduler_modal(self, open_val: bool):
        """Toggle the visibility of the scheduler modal."""
        self.show_scheduler_modal = open_val
        if open_val:
            self.scheduler_error_message = ""  # Clear previous errors

    @rx.event
    async def save_scheduled_job(self):
        """Save a new or updated scheduled job and refresh the scheduler table."""
        self.scheduler_is_loading = True
        self.scheduler_error_message = ""

        if not self.scheduler_job_name.strip() or not self.scheduler_prompt_text.strip():
            self.scheduler_error_message = "Job Name and Prompt Text cannot be empty."
            self.scheduler_is_loading = False
            return

        try:
            supabase = get_supabase_client()
            now_utc = datetime.now(timezone.utc)

            agent_id_val = None
            if self.scheduler_agent_id and self.scheduler_agent_id.strip().isdigit():
                agent_id_val = int(self.scheduler_agent_id.strip())

            payload = {
                "job_name": self.scheduler_job_name.strip(),
                "prompt_text": self.scheduler_prompt_text.strip(),
                "iteration_type": self.scheduler_iteration_type,
                "agent_id": agent_id_val,
                "status": self.scheduler_status,
                "updated_at": now_utc.isoformat()  # Always update 'updated_at'
            }

            if self.current_schedule_id is None:  # Create new job
                initial_next_run = calculate_next_run(now_utc, self.scheduler_iteration_type)
                payload['next_run_at'] = initial_next_run.isoformat()
                payload['created_at'] = now_utc.isoformat()

                response = supabase.table("scheduled_jobs").insert(payload).execute()
            else:  # Update existing job
                job_response = supabase.table("scheduled_jobs").select("iteration_type, status, next_run_at").eq("id", self.current_schedule_id).single().execute()
                if job_response.data:
                    old_job = job_response.data
                    if old_job['iteration_type'] != self.scheduler_iteration_type or \
                       (old_job['status'] == 'paused' and self.scheduler_status == 'active'):
                        new_next_run_at = calculate_next_run(now_utc, self.scheduler_iteration_type)
                        payload['next_run_at'] = new_next_run_at.isoformat()

                response = supabase.table("scheduled_jobs").update(payload).eq("id", self.current_schedule_id).execute()

            if not response:
                self.scheduler_error_message = f"Failed to save job: {response.error.message}"
            else:
                yield rx.toast(f"Scheduled job saved successfully.")
                await self.load_scheduled_jobs()  # Refresh the list
                self.show_scheduler_modal = False  # Close the modal
        except Exception as e:
            self.scheduler_error_message = f"An error occurred: {str(e)}"
        finally:
            self.scheduler_is_loading = False

    @rx.event
    async def save_prompt(self):
        """Save a new prompt, execute tasks sequentially, and update the table."""
        if not self.prompt.strip():
            yield rx.toast("Prompt cannot be empty.")
            return

        try:
            supabase = get_supabase_client()
            insert_data = {
                "prompt_text": self.prompt,
                "status": "pending_retrieval",
                "created_at": datetime.now().isoformat(),
            }
            response = supabase.table("prompts").insert(insert_data).execute()

            if response.data:
                prompt_id = response.data[0]['id']
                yield rx.toast(f"Prompt saved with Job ID: {prompt_id}. Starting first task...")
                self.prompt = ""  # Clear the input

                # Execute the first task
                # information_retrieval_task.delay(prompt_id=prompt_id, prompt_text=self.prompt)

                # # Wait for the first task to complete (simulate with status update)
                # self.update_prompt_status(prompt_id, "retrieval_complete")
                # yield rx.toast(f"First task completed for Job ID: {prompt_id}. Starting second task...")
                # await self.load_prompts()  # Refresh the table

                # # Execute the second task
                # process_and_summarize_task.delay(prompt_id=prompt_id)

                # # Wait for the second task to complete (simulate with status update)
                # self.update_prompt_status(prompt_id, "summary_complete")
                # yield rx.toast(f"Second task completed for Job ID: {prompt_id}. Starting third task...")
                # await self.load_prompts()  # Refresh the table

                # # Execute the third task (if applicable)
                # # Simulate third task completion
                # self.update_prompt_status(prompt_id, "completed")
                # yield rx.toast(f"All tasks completed for Job ID: {prompt_id}. Prompt processing finished.")
                # await self.load_prompts()  # Refresh the table
            else:
                yield rx.toast.error(f"Failed to save prompt: {response.error.message if response.error else 'Unknown error'}")
        except Exception as e:
            yield rx.toast.error(f"An error occurred: {str(e)}")

    @rx.event
    async def update_prompt_status(self, prompt_id: int, new_status: str):
        """Update the status of a prompt in the database and refresh the table."""
        try:
            supabase = get_supabase_client()
            update_data = {
                "status": new_status,
                "updated_at": datetime.now().isoformat(),
            }
            response = supabase.table("prompts").update(update_data).eq("id", prompt_id).execute()
            if not response:
                yield rx.toast.error(f"Failed to update status for Job ID {prompt_id}: {response.error.message}")
            else:
                await self.load_prompts()  # Refresh the table
        except Exception as e:
            yield rx.toast.error(f"An error occurred while updating status: {str(e)}")

    @rx.event
    async def load_prompts(self):
        """Load all prompts from the database, ordered by jobId and status."""
        try:
            supabase = get_supabase_client()
            response = supabase.table("prompts").select("*").order("id", desc=True).order("status", desc=True).execute()
            if response.data:
                self.prompts = response.data
            else:
                self.prompts = []
        except Exception as e:
            yield rx.toast.error(f"Failed to load prompts: {str(e)}")

    @rx.event
    async def delete_prompt(self, prompt_id: int):
        """Delete a specific prompt only if it is in completed status."""
        try:
            # Find the prompt in the list
            prompt = next((p for p in self.prompts if p["id"] == prompt_id), None)
            if not prompt:
                yield rx.toast(f"Cannot delete prompt with Job ID {prompt_id}. Only completed prompts can be deleted.")
                return

            supabase = get_supabase_client()
            response = supabase.table("prompts").delete().eq("id", prompt_id).execute()
            if not response:
                yield rx.toast.error(f"Failed to delete prompt: {response.error.message}")
            else:
                yield rx.toast(f"Prompt with Job ID {prompt_id} deleted.")
                await self.load_prompts()  # Refresh the table
        except Exception as e:
            yield rx.toast.error(f"An error occurred: {str(e)}")

    @rx.event
    async def archive_prompt(self, prompt_id: int):
        """Archive a specific prompt by moving it to the archived_prompts table."""
        try:
            # Find the prompt in the list
            yield rx.toast(f"Archived prompt with Job ID {prompt_id}...")
            prompt = next((p for p in self.prompts if p["id"] == prompt_id), None)
            if not prompt:
                yield rx.toast.error(f"Cannot archive prompt with Job ID {prompt_id}. Only completed prompts can be archived.")
                return

            supabase = get_supabase_client()
            # Insert the prompt into the archived_prompts table
            archive_data = {
                "source_job_id": prompt["source_job_id"],
                "agent_id": prompt["agent_id"],
                "user_id": prompt["user_id"],
                "prompt_text": prompt["prompt_text"],
                "status": prompt["status"],
                "created_at": prompt["created_at"],
                "archived_at": datetime.now().isoformat(),
            }
            archive_response = supabase.table("archived_prompts").insert(archive_data).execute()
            if not archive_response:
                yield rx.toast(f"Failed to archive prompt: {archive_response.error.message}")
                return

            # Delete the prompt from the original prompts table
            delete_response = supabase.table("prompts").delete().eq("id", prompt_id).execute()
            if not delete_response:
                yield rx.toast.error(f"Failed to delete prompt after archiving: {delete_response.error.message}")
                return

            yield rx.toast(f"Prompt with Job ID {prompt_id} archived successfully.")
            await self.load_prompts()  # Refresh the table
        except Exception as e:
            yield rx.toast.error(f"An error occurred: {str(e)}")

    @rx.event
    async def refresh_status(self, prompt_id: int):
        """Refresh the status of a specific prompt."""
        try:
            supabase = get_supabase_client()
            response = supabase.table("prompts").select("status").eq("id", prompt_id).single().execute()
            if response.data:
                for prompt in self.prompts:
                    if prompt["id"] == prompt_id:
                        prompt["status"] = response.data["status"]
                        break
                yield rx.toast(f"Status updated for Job ID: {prompt_id}")
            else:
                yield rx.toast.error(f"Failed to refresh status for Job ID: {prompt_id}")
        except Exception as e:
            yield rx.toast.error(f"An error occurred: {str(e)}")

    @rx.event
    async def resend_prompt(self, prompt_id: int):
        """Reset the status of the same prompt and recall the first step task."""
        try:
            supabase = get_supabase_client()
            response = supabase.table("prompts").select("prompt_text").eq("id", prompt_id).single().execute()
            if response.data:
                # Update the prompt status to the first step
                update_data = {
                    "status": "pending",
                    "updated_at": datetime.now().isoformat(),
                }
                update_response = supabase.table("prompts").update(update_data).eq("id", prompt_id).execute()
                if not update_response:
                    yield rx.toast.error(f"Failed to reset prompt status: {update_response.error.message}")
                    return

                # Recall the first step task
                information_retrieval_task.delay(prompt_id=prompt_id, prompt_text=response.data["prompt_text"])
                yield rx.toast(f"Prompt with Job ID {prompt_id} has been reset and task recalled.")
                await self.load_prompts()  # Refresh the table
            else:
                yield rx.toast.error(f"Failed to fetch prompt text for Job ID: {prompt_id}")
        except Exception as e:
            yield rx.toast.error(f"An error occurred: {str(e)}")

    @rx.event
    async def load_archived_prompts(self):
        """Load all archived prompts from the database."""
        try:
            supabase = get_supabase_client()
            response = supabase.table("archived_prompts").select("*").order("archived_at", desc=True).execute()
            if response.data:
                self.archived_prompts = response.data
            else:
                self.archived_prompts = []
        except Exception as e:
            self.archived_error_message = f"Failed to load archived prompts: {str(e)}"

    @rx.event
    async def restore_prompt(self, archived_id: int):
        """Restore a prompt from the archived_prompts table to the original prompts table."""
        try:
            supabase = get_supabase_client()
            response = supabase.table("archived_prompts").select("*").eq("id", archived_id).single().execute()
            if response.data:
                restore_data = {
                    "prompt_text": response.data["prompt_text"],
                    "status": "pending",
                    "created_at": response.data["created_at"],
                }
                restore_response = supabase.table("prompts").insert(restore_data).execute()
                if not restore_response:
                    self.archived_error_message = f"Failed to restore prompt: {restore_response.error.message}"
                    return

                delete_response = supabase.table("archived_prompts").delete().eq("id", archived_id).execute()
                if not delete_response:
                    self.archived_error_message = f"Failed to delete prompt from archived table: {delete_response.error.message}"
                    return

                yield rx.toast(f"Prompt with ID {archived_id} restored successfully.")
                await self.load_archived_prompts()  # Refresh the archived table
            else:
                self.archived_error_message = f"Failed to fetch archived prompt with ID {archived_id}."
        except Exception as e:
            self.archived_error_message = f"An error occurred: {str(e)}"

    @rx.event
    async def delete_archived_prompt(self, archived_id: int):
        """Delete a prompt from the archived_prompts table."""
        try:
            supabase = get_supabase_client()
            response = supabase.table("archived_prompts").delete().eq("id", archived_id).execute()
            if not response:
                self.archived_error_message = f"Failed to delete archived prompt: {response.error.message}"
            yield rx.toast(f"Archived prompt with ID {archived_id} deleted successfully.")
            await self.load_archived_prompts()  # Refresh the archived table
        except Exception as e:
            self.archived_error_message = f"An error occurred: {str(e)}"

    @rx.event
    async def set_show_archived_modal(self, open_val: bool):
        """Toggle the visibility of the archived prompts modal."""
        await self.load_archived_prompts()  # Load archived prompts when opening the modal
        self.show_archived_modal = open_val
        if open_val:
            self.archived_error_message = ""  # Clear previous errors

    @rx.event
    async def load_scheduled_jobs(self):
        """Load all scheduled jobs from the database."""
        self.scheduler_is_loading = True
        self.scheduled_jobs = []
        self.scheduler_error_message = ""
        yield rx.toast("Loading scheduled jobs...")
        try:
            supabase = get_supabase_client()
            response = supabase.table("scheduled_jobs").select("*").order("created_at", desc=True).execute()
            if response.data:
                self.scheduled_jobs = response.data
            else:
                if not response:
                    self.scheduler_error_message = f"Failed to load scheduled jobs: {response.error.message}"
                else:
                    self.scheduler_error_message = "No scheduled jobs found or failed to load."
        except Exception as e:
            self.scheduler_error_message = f"An error occurred while loading jobs: {str(e)}"
        finally:
            self.scheduler_is_loading = False

    @rx.event
    async def delete_scheduled_job(self, schedule_id: int):
        """Delete a scheduled job from the database."""
        self.scheduler_is_loading = True
        self.scheduler_error_message = ""
        try:
            supabase = get_supabase_client()
            response = supabase.table("scheduled_jobs").delete().eq("id", schedule_id).execute()
            if not response:
                self.scheduler_error_message = f"Failed to delete scheduled job: {response.error.message}"
            else:
                yield rx.toast(f"Scheduled job with ID {schedule_id} deleted successfully.")
                await self.load_scheduled_jobs()  # Refresh the list of scheduled jobs
        except Exception as e:
            self.scheduler_error_message = f"An error occurred while deleting the job: {str(e)}"
        finally:
            self.scheduler_is_loading = False

    @rx.event
    async def run_scheduled_job_now(self, schedule_id: int):
        """Manually trigger a scheduled job to run immediately."""
        self.scheduler_is_loading = True
        self.scheduler_error_message = ""
        try:
            # Call the Celery task to force run the job
            force_run_scheduled_job_task.delay(schedule_id)
            yield rx.toast(f"Manual run for job ID {schedule_id} has been requested.")
            await self.load_scheduled_jobs()  # Refresh the list of scheduled jobs
        except Exception as e:
            self.scheduler_error_message = f"Failed to trigger manual run for job ID {schedule_id}: {str(e)}"
        finally:
            self.scheduler_is_loading = False

    @rx.event
    async def toggle_scheduled_job_status(self, schedule_id: int, current_status: str):
        """Toggle the status of a scheduled job between 'active' and 'paused'."""
        self.scheduler_is_loading = True
        self.scheduler_error_message = ""
        try:
            supabase = get_supabase_client()
            now_utc = datetime.now(timezone.utc)
            new_status = "paused" if current_status == "active" else "active"

            payload = {
                "status": new_status,
                "updated_at": now_utc.isoformat()
            }

            if new_status == "active":
                # If reactivating, check if next_run_at is in the past.
                # If so, recalculate it from now to ensure it runs soon.
                job_response = supabase.table("scheduled_jobs").select("next_run_at, iteration_type").eq("id", schedule_id).single().execute()
                if job_response.data:
                    db_next_run_at_str = job_response.data['next_run_at']
                    db_iteration_type = job_response.data['iteration_type']
                    db_next_run_at = datetime.fromisoformat(db_next_run_at_str.replace('Z', '+00:00'))
                    if db_next_run_at <= now_utc:
                        payload['next_run_at'] = calculate_next_run(db_next_run_at, db_iteration_type).isoformat()

            response = supabase.table("scheduled_jobs").update(payload).eq("id", schedule_id).execute()

            if not response:
                self.scheduler_error_message = f"Failed to toggle status for job ID {schedule_id}: {response.error.message}"
            else:
                yield rx.toast(f"Job ID {schedule_id} status updated to '{new_status}'.")
                await self.load_scheduled_jobs()  # Refresh the list of scheduled jobs
        except Exception as e:
            self.scheduler_error_message = f"An error occurred while toggling status for job ID {schedule_id}: {str(e)}"
        finally:
            self.scheduler_is_loading = False

    @rx.event
    async def view_last_run_details(self, prompt_id: int):
        """Fetch and display the details of the last run in a modal."""
        self.show_last_run_modal = True
        self.last_run_details = ""
        self.last_run_error_message = ""
        try:
            supabase = get_supabase_client()
            response = supabase.table("results").select("summary").eq("prompt_id", prompt_id).single().execute()
            if response.data:
                self.last_run_details = response.data.get("summary", "No summary available.")
            else:
                self.last_run_error_message = f"No details found for prompt ID {prompt_id}."
        except Exception as e:
            self.last_run_error_message = f"An error occurred while fetching details: {str(e)}"

    @rx.event
    def set_show_last_run_modal(self, open_val: bool):
        """Toggle the visibility of the last run details modal."""
        self.show_last_run_modal = open_val
        if not open_val:
            self.last_run_details = ""
            self.last_run_error_message = ""

    @rx.event
    def handle_submit(self):
        if not self.prompt.strip():
            self.error_message = "Prompt cannot be empty."
            return

        self.is_loading = True
        self.result = "Submitting prompt..."
        self.error_message = ""
        self.summary = ""
        self.processed_options = []
        self.current_prompt_id = None # Reset from previous submission

        try:
            supabase = get_supabase_client()
            
            # Insert into prompts table
            insert_data = {
                "prompt_text": self.prompt,
                "status": "pending_retrieval", # Initial status
                "created_at": datetime.now().isoformat()
            }
            response = supabase.table("prompts").insert(insert_data).execute()

            if response.data and len(response.data) > 0:
                self.current_prompt_id = response.data[0]['id']
                self.result = f"Prompt submitted (ID: {self.current_prompt_id}). Processing..."
                
                # Call the first Celery task
                information_retrieval_task.delay(prompt_id=self.current_prompt_id, prompt_text=self.prompt)
                # Optionally, chain the next task if retrieval is synchronous or handle it purely by status
                # For now, let's assume information_retrieval_task will trigger process_and_summarize_task
                # or we'll rely on status checks. The original plan has them separate.
                # process_and_summarize_task.delay(prompt_id=self.current_prompt_id) # This might be premature

            else:
                self.error_message = f"Failed to submit prompt. Supabase response: {response.error.message if response.error else 'No data returned'}"
                self.result = "" # Clear general result message
        except Exception as e:
            self.error_message = f"An error occurred during submission: {str(e)}"
            self.result = "" # Clear general result message
        finally:
            self.is_loading = False # Allow user to refresh or submit again if needed

    @rx.event
    def fetch_results(self):
        if self.current_prompt_id is None:
            self.error_message = "No prompt has been submitted yet, or submission failed."
            return

        self.is_loading = True
        self.error_message = ""
        self.result = "Fetching results..." # Clear previous result message
        self.summary = "" # Clear previous summary
        self.processed_options = [] # Clear previous options

        try:
            supabase = get_supabase_client()
            
            # Check prompt status
            prompt_response = supabase.table("prompts").select("status").eq("id", self.current_prompt_id).single().execute()

            if prompt_response.data:
                current_status = prompt_response.data['status']
                if current_status == "completed":
                    # Fetch from results table
                    # Assuming one result row per prompt_id, or fetch the latest
                    results_response = supabase.table("results").select("processed_options, summary").eq("prompt_id", self.current_prompt_id).order("created_at", desc=True).limit(1).execute()
                    
                    if results_response.data and len(results_response.data) > 0:
                        result_data = results_response.data[0]
                        self.summary = result_data.get("summary", "Summary not available.")
                        
                        options_json = result_data.get("processed_options", "[]")
                        try:
                            self.processed_options = json.loads(options_json)
                            if not isinstance(self.processed_options, list):
                                self.processed_options = [str(self.processed_options)] # Ensure it's a list
                        except json.JSONDecodeError:
                            self.processed_options = ["Error: Could not parse options."]
                        
                        self.result = "Results loaded."
                    else:
                        self.error_message = f"Results not found for prompt ID {self.current_prompt_id}, though status is 'completed'."
                        self.result = ""
                elif current_status == "retrieval_complete":
                     self.result = f"Status: {current_status}. Summary generation is pending. Click Refresh again shortly."
                     # Trigger the next task if it hasn't been triggered automatically
                     # This is a good place to ensure the summarization task is called
                     process_and_summarize_task.delay(prompt_id=self.current_prompt_id, agent_id=1) # Assuming agent_id is not needed here, or set to None     
                elif current_status == "retrieval_error":
                    self.error_message = "An error occurred while fetching information. Please try submitting again or contact support if the issue persists."
                    self.result = "" # Clear general result message
                    self.summary = ""
                    self.processed_options = []
                elif current_status in ["summary_error_config", "summary_error"]:
                    self.error_message = "An error occurred while processing the results. Please try again or contact support."
                    self.result = "" # Clear general result message
                    self.summary = ""
                    self.processed_options = []                
                else: # Catch-all for other statuses or unexpected ones
                    self.result = f"Processing is not yet complete. Current status: {current_status}"
                    self.summary = ""
                    self.processed_options = []
            else:
                self.error_message = f"Could not fetch status for prompt ID {self.current_prompt_id}. Supabase: {prompt_response.error.message if prompt_response.error else 'No data'}"
                self.result = ""

        except Exception as e:
            self.error_message = f"An error occurred while fetching results: {str(e)}"
            self.result = ""
        finally:
            self.is_loading = False