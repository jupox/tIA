import reflex as rx
from .models import Prompt, Result # Assuming models.py might be used for Pydantic types if needed by Reflex state
from .utils import get_supabase_client
from .tasks import information_retrieval_task, process_and_summarize_task, force_run_scheduled_job_task # Import Celery tasks
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
                "user_prompt": self.prompt,
                "status": "pending_retrieval", # Initial status
                "created_at": datetime.now().isoformat()
            }
            response = supabase.table("prompts").insert(insert_data).execute()

            if response.data and len(response.data) > 0:
                self.current_prompt_id = response.data[0]['id']
                self.result = f"Prompt submitted (ID: {self.current_prompt_id}). Processing..."
                
                # Call the first Celery task
                information_retrieval_task.delay(prompt_id=self.current_prompt_id, user_prompt=self.prompt)
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
                     process_and_summarize_task.delay(prompt_id=self.current_prompt_id)                
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

    # --- Scheduler Methods ---

    def _calculate_initial_next_run(self, iteration_type: str, base_time: datetime) -> datetime:
        """
        Calculates the initial next_run_at time for a new scheduled job.
        Ensures the calculated time is in the future relative to base_time.
        base_time must be timezone-aware (UTC).
        """
        if base_time.tzinfo is None:
            raise ValueError("base_time must be timezone-aware")

        # Normalize base_time for calculations involving start of hour/day
        base_time_for_calc = base_time

        if iteration_type == "hourly":
            # Next hour, top of the hour
            next_run = base_time_for_calc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            # If base_time_for_calc was already at the top of an hour, this would be correct.
            # If base_time_for_calc was e.g. 10:30, next_run would be 11:00.
            # If current time is 10:59, next run is 11:00.
            # What if current time is 10:00, does user expect 11:00 or 10:00 if job is created at 10:00:01?
            # The current logic sets it to next hour's 00 minute.
            # To run at current hour's 00 minute if not passed, or next hour's 00 minute if passed:
            potential_run = base_time_for_calc.replace(minute=0, second=0, microsecond=0)
            if potential_run > base_time_for_calc: # e.g. current 09:50, potential_run 09:00 (past for this hour calc)
                 next_run = potential_run + timedelta(hours=1) # so 10:00
            elif potential_run == base_time_for_calc : # current is 09:00:00, job created, run at 10:00:00
                 next_run = potential_run + timedelta(hours=1)
            else: # current e.g. 09:30, potential_run 09:00. We want next hour.
                 next_run = potential_run + timedelta(hours=1) # So 10:00

            # Simplified: always next hour, top of the hour from current time.
            next_run = (base_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))


        elif iteration_type == "daily":
            # Next day, at 00:00 UTC
            next_run = (base_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))

        elif iteration_type.startswith("weekly_"):
            days_map = {
                "weekly_monday": 0, "weekly_tuesday": 1, "weekly_wednesday": 2,
                "weekly_thursday": 3, "weekly_friday": 4, "weekly_saturday": 5,
                "weekly_sunday": 6
            }
            target_weekday = days_map[iteration_type]

            current_weekday = base_time.weekday() # Monday is 0 and Sunday is 6
            days_ahead = (target_weekday - current_weekday + 7) % 7

            next_run_date = base_time + timedelta(days=days_ahead)
            next_run = next_run_date.replace(hour=0, minute=0, second=0, microsecond=0)

            # If calculated next_run is today but already past, or if days_ahead is 0 (today)
            # and time is past 00:00, schedule for next week.
            if next_run <= base_time :
                next_run += timedelta(days=7)
        else:
            # Fallback for unknown type, schedule for next day
            next_run = (base_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))

        # Final check to ensure it's always in the future from the original base_time
        # This is particularly important if logic above results in same day but earlier time.
        if next_run <= base_time:
             # This case should ideally be handled by specific logic above, e.g. for weekly.
             # For hourly, if base_time is 10:30, next_run (11:00) > base_time.
             # For daily, if base_time is 10:30, next_run (tomorrow 00:00) > base_time.
             # If it's weekly and today but past midnight, it adds 7 days.
             # This is a safeguard.
             if iteration_type == "hourly":
                 next_run += timedelta(hours=1)
             else: # daily, weekly
                 next_run += timedelta(days=1) # or days=7 for weekly if it's same day past. More refined logic is in weekly.
                 # For safety, if weekly logic produced a past/same time, just push by a day.
                 # The weekly logic itself should be robust.
                 # If it's still not in future, then there's an issue.
                 # The current weekly logic ensures it's next week if today is past.

        return next_run

    async def load_scheduled_jobs(self):
        self.scheduler_is_loading = True
        self.scheduled_jobs = []
        self.scheduler_error_message = ""
        try:
            supabase = get_supabase_client()
            response = supabase.table("scheduled_jobs").select("*").order("created_at", desc=True).execute()
            if response.data:
                self.scheduled_jobs = response.data
            else:
                if response.error:
                    self.scheduler_error_message = f"Failed to load scheduled jobs: {response.error.message}"
                else:
                    self.scheduler_error_message = "No scheduled jobs found or failed to load." # Should be rare without error
        except Exception as e:
            self.scheduler_error_message = f"An error occurred while loading jobs: {str(e)}"
        finally:
            self.scheduler_is_loading = False

    def open_scheduler_modal(self, schedule_data: dict | None = None):
        self.scheduler_error_message = "" # Clear previous errors
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

    def close_scheduler_modal(self):
        self.show_scheduler_modal = False
        self.current_schedule_id = None
        self.scheduler_job_name = ""
        self.scheduler_prompt_text = ""
        self.scheduler_iteration_type = "daily"
        self.scheduler_agent_id = ""
        self.scheduler_status = "active"
        self.scheduler_error_message = "" # Clear errors on close

    async def save_scheduled_job(self):
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
                "updated_at": now_utc.isoformat() # Always update 'updated_at'
            }

            if self.current_schedule_id is None: # Create new job
                initial_next_run = self._calculate_initial_next_run(self.scheduler_iteration_type, now_utc)
                payload['next_run_at'] = initial_next_run.isoformat()
                payload['created_at'] = now_utc.isoformat()
                # last_run_at, last_prompt_id, last_run_status are not set on creation

                response = supabase.table("scheduled_jobs").insert(payload).execute()
            else: # Update existing job
                # Check if iteration_type or status changed to active from paused, to recalculate next_run_at
                # For simplicity, if iteration type changes, we recalculate next_run_at from now.
                # Fetch existing job to compare
                job_response = supabase.table("scheduled_jobs").select("iteration_type, status, next_run_at").eq("id", self.current_schedule_id).single().execute()
                if job_response.data:
                    old_job = job_response.data
                    if old_job['iteration_type'] != self.scheduler_iteration_type or \
                       (old_job['status'] == 'paused' and self.scheduler_status == 'active'):
                        # If type changed, or if reactivated, calculate next run from now.
                        # If it was already active and type didn't change, next_run_at is preserved unless manually changed by a future feature.

                        # Parse existing next_run_at to ensure it's a datetime object for _calculate_initial_next_run
                        # This part needs to be careful: if user changes iteration type, do we base off old next_run_at or now?
                        # Basing off 'now_utc' is safer to ensure it's in the future and reflects the change promptly.
                        new_next_run_at = self._calculate_initial_next_run(self.scheduler_iteration_type, now_utc)

                        # However, if the job was paused and is now active, and its next_run_at is in the future,
                        # we might want to keep it. The scheduler_dispatcher_task already handles past next_run_at.
                        # For now, let's be consistent: if iteration_type changes, or if status changes to 'active',
                        # recalculate from 'now_utc'. This provides a predictable behavior.
                        if old_job['iteration_type'] != self.scheduler_iteration_type:
                             payload['next_run_at'] = self._calculate_initial_next_run(self.scheduler_iteration_type, now_utc).isoformat()
                        elif old_job['status'] == 'paused' and self.scheduler_status == 'active':
                            # If reactivating, and next_run_at from DB is in past, recalculate from now. Otherwise, keep future one.
                            db_next_run_at = datetime.fromisoformat(old_job['next_run_at'].replace('Z', '+00:00'))
                            if db_next_run_at <= now_utc:
                                payload['next_run_at'] = self._calculate_initial_next_run(self.scheduler_iteration_type, now_utc).isoformat()
                            else:
                                payload['next_run_at'] = db_next_run_at.isoformat() # Keep the future scheduled time

                response = supabase.table("scheduled_jobs").update(payload).eq("id", self.current_schedule_id).execute()

            if response.error:
                self.scheduler_error_message = f"Failed to save job: {response.error.message}"
            else:
                self.close_scheduler_modal()
                await self.load_scheduled_jobs() # Refresh the list

        except Exception as e:
            self.scheduler_error_message = f"An error occurred: {str(e)}"
        finally:
            self.scheduler_is_loading = False

    async def delete_scheduled_job(self, schedule_id: int):
        self.scheduler_is_loading = True
        self.scheduler_error_message = ""
        try:
            supabase = get_supabase_client()
            response = supabase.table("scheduled_jobs").delete().eq("id", schedule_id).execute()
            if response.error:
                self.scheduler_error_message = f"Failed to delete job: {response.error.message}"
            else:
                await self.load_scheduled_jobs() # Refresh list
        except Exception as e:
            self.scheduler_error_message = f"An error occurred: {str(e)}"
        finally:
            self.scheduler_is_loading = False

    async def toggle_scheduled_job_status(self, schedule_id: int, current_status: str):
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
                # If so, recalculate it from now to ensure it runs soon, not immediately if scheduler is quick.
                job_response = supabase.table("scheduled_jobs").select("next_run_at, iteration_type").eq("id", schedule_id).single().execute()
                if job_response.data:
                    db_next_run_at_str = job_response.data['next_run_at']
                    db_iteration_type = job_response.data['iteration_type']
                    db_next_run_at = datetime.fromisoformat(db_next_run_at_str.replace('Z', '+00:00'))
                    if db_next_run_at <= now_utc:
                        payload['next_run_at'] = self._calculate_initial_next_run(db_iteration_type, now_utc).isoformat()
                else:
                    # Fallback if job data couldn't be fetched, though unlikely if we are toggling it.
                    # Don't change next_run_at in this case.
                    pass

            response = supabase.table("scheduled_jobs").update(payload).eq("id", schedule_id).execute()

            if response.error:
                self.scheduler_error_message = f"Failed to toggle status: {response.error.message}"
            else:
                await self.load_scheduled_jobs() # Refresh list
        except Exception as e:
            self.scheduler_error_message = f"An error occurred: {str(e)}"
        finally:
            self.scheduler_is_loading = False

    async def run_scheduled_job_now(self, schedule_id: int):
        self.scheduler_is_loading = True # Use a general loading or a specific one for this action
        self.scheduler_error_message = ""
        try:
            # Call the Celery task to force run the job
            force_run_scheduled_job_task.delay(schedule_id)
            # Provide immediate feedback to the user.
            # The actual status of the run will be updated by the task in the DB.
            # Consider adding a toast message here if your UI framework supports it easily.
            # For now, a message in the scheduler error field or a dedicated status field.
            self.scheduler_error_message = f"Manual run for job ID {schedule_id} has been requested. The job's 'Last Run Status' will update upon completion."
            # Optionally, you could refresh the jobs list after a short delay
            # or rely on the user to manually refresh.
            # For example:
            # await asyncio.sleep(5) # Requires import asyncio
            # await self.load_scheduled_jobs()
        except Exception as e:
            self.scheduler_error_message = f"Failed to trigger manual run for job ID {schedule_id}: {str(e)}"
        finally:
            self.scheduler_is_loading = False # Reset loading state

    def view_last_run_details(self, prompt_id: int | None):
        if prompt_id is not None:
            self.current_prompt_id = prompt_id
            # Potentially clear previous results related to non-scheduled prompts
            self.result = "Fetching results for last scheduled run..."
            self.summary = ""
            self.processed_options = []
            self.error_message = "" # Clear main error message
            self.scheduler_error_message = "" # Clear scheduler specific error message
            # Call the existing method to load results; this method handles its own loading state
            return self.fetch_results
        else:
            # Update scheduler_error_message as this action originates from scheduler UI
            self.scheduler_error_message = "No last run details available for this job (no prompt ID found)."
            # Clear main result display areas
            self.result = ""
            self.summary = ""
            self.processed_options = []


# --- UI Components for Scheduler ---

def scheduler_modal() -> rx.Component:
    """UI for creating and editing scheduled jobs."""
    return rx.modal(
        rx.modal_overlay(
            rx.modal_content(
                rx.modal_header(State.scheduler_modal_title),
                rx.modal_body(
                    rx.form.root(
                        rx.vstack(
                            rx.form.field(
                                rx.form.label("Job Name"),
                                rx.input(
                                    placeholder="Enter a descriptive name for the job",
                                    value=State.scheduler_job_name,
                                    on_change=State.set_scheduler_job_name,
                                    width="100%",
                                ),
                                name="scheduler_job_name",
                                width="100%",
                            ),
                            rx.form.field(
                                rx.form.label("Prompt Text"),
                                rx.text_area(
                                    placeholder="Enter the full prompt text for the job",
                                    value=State.scheduler_prompt_text,
                                    on_change=State.set_scheduler_prompt_text,
                                    width="100%",
                                    rows=5,
                                ),
                                name="scheduler_prompt_text",
                                width="100%",
                            ),
                            rx.form.field(
                                rx.form.label("Iteration"),
                                rx.select(
                                    State.iteration_options, # expects list of dicts with 'label' and 'value'
                                    placeholder="Select iteration type",
                                    value=State.scheduler_iteration_type,
                                    on_change=State.set_scheduler_iteration_type,
                                    width="100%",
                                ),
                                name="scheduler_iteration_type",
                                width="100%",
                            ),
                            rx.form.field(
                                rx.form.label("Agent ID (Optional)"),
                                rx.input(
                                    placeholder="Enter numeric Agent ID if applicable",
                                    value=State.scheduler_agent_id,
                                    on_change=State.set_scheduler_agent_id,
                                    width="100%",
                                ),
                                name="scheduler_agent_id",
                                width="100%",
                            ),
                            rx.form.field(
                                rx.form.label("Status"),
                                rx.select(
                                    [
                                        {"label": "Active", "value": "active"},
                                        {"label": "Paused", "value": "paused"},
                                    ],
                                    placeholder="Select status",
                                    value=State.scheduler_status,
                                    on_change=State.set_scheduler_status,
                                    width="100%",
                                ),
                                name="scheduler_status",
                                width="100%",
                            ),
                            rx.cond(
                                State.scheduler_error_message != "",
                                rx.callout(
                                    State.scheduler_error_message,
                                    icon="alert_triangle",
                                    color_scheme="red",
                                    role="alert",
                                    width="100%",
                                ),
                                rx.fragment()
                            ),
                            spacing="3",
                            width="100%",
                        ),
                        on_submit=State.save_scheduled_job, # Allow Enter to submit form
                        reset_on_submit=False, # Keep form data for inspection on error
                        width="100%",
                    )
                ),
                rx.modal_footer(
                    rx.button("Cancel", on_click=State.close_scheduler_modal, variant="soft"),
                    rx.button(
                        "Save Job",
                        on_click=State.save_scheduled_job,
                        is_loading=State.scheduler_is_loading
                    ),
                ),
            )
        ),
        is_open=State.show_scheduler_modal,
        on_close=State.close_scheduler_modal, # Allow closing with Esc key or overlay click
    )

def scheduled_jobs_table() -> rx.Component:
    """UI table to display scheduled jobs."""
    return rx.box(
        rx.heading("Scheduled Jobs Management", size="5", margin_bottom="1em"),
        rx.hstack(
            rx.button("Load / Refresh Schedules", on_click=State.load_scheduled_jobs, is_loading=State.scheduler_is_loading),
            rx.button("Create New Scheduled Job", on_click=lambda: State.open_scheduler_modal(None)),
            spacing="3",
            margin_bottom="1em",
        ),
        rx.cond(
            State.scheduler_error_message != "",
             rx.callout(
                State.scheduler_error_message, # Display errors from loading/actions here too
                icon="alert_triangle",
                color_scheme="red",
                role="alert",
                margin_bottom="1em",
            ),
            rx.fragment()
        ),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Job Name"),
                    rx.table.column_header_cell("Prompt Snippet"),
                    rx.table.column_header_cell("Iteration"),
                    rx.table.column_header_cell("Next Run (UTC)"),
                    rx.table.column_header_cell("Last Run (UTC)"),
                    rx.table.column_header_cell("Status"),
                    rx.table.column_header_cell("Last Run Status"),
                    rx.table.column_header_cell("Actions"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    State.scheduled_jobs,
                    lambda job: rx.table.row(
                        rx.table.cell(job.get("job_name", "N/A")),
                        rx.table.cell(rx.text(job.get("prompt_text", "")[:30] + "...", title=job.get("prompt_text", ""))), # Show snippet, full on hover
                        rx.table.cell(job.get("iteration_type", "N/A")),
                        rx.table.cell(job.get("next_run_at", "N/A")), # Needs formatting
                        rx.table.cell(job.get("last_run_at", "N/A")), # Needs formatting
                        rx.table.cell(job.get("status", "N/A")),
                        rx.table.cell(job.get("last_run_status", "N/A")),
                        rx.table.cell(
                            rx.hstack(
                                rx.button("Edit", on_click=lambda: State.open_scheduler_modal(job), size="1", variant="outline"),
                                rx.button(
                                    rx.cond(job.get("status") == "active", "Pause", "Resume"),
                                    on_click=lambda: State.toggle_scheduled_job_status(job["id"], job.get("status","")),
                                    size="1",
                                    variant="outline",
                                ),
                                rx.button("Run Now", on_click=lambda: State.run_scheduled_job_now(job["id"]), size="1", variant="outline"),
                                rx.button("View Last Run",
                                          on_click=State.view_last_run_details(job.get("last_prompt_id")),
                                          size="1",
                                          variant="outline",
                                          is_disabled=job.get("last_prompt_id").is_none()
                                ),
                                rx.button("Delete", on_click=lambda: State.delete_scheduled_job(job["id"]), color_scheme="red", size="1", variant="solid"),
                                spacing="1",
                            )
                        ),
                    ),
                )
            ),
        ),
        width="100%",
        margin_top="2em", # Space above the table section
    )


def index():
    return rx.container(
        rx.vstack(
            rx.heading("AI Decision Support Tool Task", size="9"),
            rx.heading("Task IA - TIA", size="6", margin_bottom="1em"),
            
            # Main Prompt Area
            rx.heading("Manual Prompt Submission", size="5", margin_top="1em", margin_bottom="0.5em"),
            rx.input(
                placeholder="Enter your decision prompt here...",
                value=State.prompt, # Ensure two-way binding if needed or use on_change
                on_change=State.set_prompt, # Or on_blur if preferred
                style={"margin_bottom": "0.5em", "width": "100%"},
                is_disabled=State.is_loading,
            ),
            
            rx.hstack(
                rx.button(
                    "Submit Prompt",
                    on_click=State.handle_submit,
                    is_loading=State.is_loading,
                    is_disabled=State.is_loading,
                ),
                rx.button(
                    "Refresh Results",
                    on_click=State.fetch_results,
                    is_disabled=rx.cond(State.current_prompt_id.is_none() | State.is_loading, True, False),
                ),
                # Removed Manage Schedules button from here, will be part of scheduled_jobs_table section
                spacing="3", # Increased spacing
                style={"margin_bottom": "1em"}
            ),
            
            # Main Display area for manual prompts
            rx.vstack(
                rx.cond(
                    State.error_message != "",
                    rx.callout( # Using rx.callout for better styling of errors
                        State.error_message,
                        icon="alert_triangle",
                        color_scheme="red",
                        role="alert",
                        width="100%",
                        margin_bottom="1em"
                    ),
                    rx.fragment()
                ),

                rx.text(State.result, margin_bottom="0.5em", font_style="italic"),

                rx.cond(
                    State.summary != "",
                    rx.box( # Using rx.box for better structure and potential styling
                        rx.heading("Summary:", size="4", margin_bottom="0.5em"), # Smaller heading
                        rx.text(State.summary, white_space="pre-wrap"),
                        width="100%",
                        padding_y="0.5em", # Padding for vertical space
                    ),
                    rx.fragment()
                ),

                rx.cond(
                    State.processed_options.length() > 0,
                    rx.box(
                        rx.heading("Processed Options:", size="4", margin_bottom="0.5em"),
                        rx.list.ordered(
                            items=State.processed_options,
                            # render_item=lambda item: rx.list.item(rx.text(item)), # Corrected render_item
                        ),
                        width="100%",
                        padding_y="0.5em",
                    ),
                    rx.fragment()
                ),
                spacing="2", # Increased spacing
                width="100%",
                padding="1em",
                border="1px solid #ddd",
                border_radius="md",
                min_height="150px" # Adjusted min height
            ),

            rx.divider(width="100%", margin_y="2em"), # Visual separator

            # Scheduler UI Section
            scheduled_jobs_table(), # Add the table here

            # The modal is not placed visually here, but its definition makes it available
            scheduler_modal(),

            spacing="4", # Overall vstack spacing
            width="100%"
        ),
        padding="2em",
        max_width="1000px", # Wider max_width for table
        margin="auto"
    )

# Add state and page to the app.
app = rx.App(state=State) # Ensure State is passed if not default
app.add_page(index, title="AI Decision Support") # Add a title to the page
# Not calling app.compile() here as it's usually handled by Reflex CLI
