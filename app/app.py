import reflex as rx
from .models import Prompt, Result # Assuming models.py might be used for Pydantic types if needed by Reflex state
from .utils import get_supabase_client
from .tasks import information_retrieval_task, process_and_summarize_task # Import Celery tasks
from datetime import datetime
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
                else:
                    self.result = f"Processing is not yet complete. Current status: {current_status}"
                    # Clear previous data if status is just pending
                    self.summary = ""
                    self.processed_options = []
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


def index():
    return rx.container(
        rx.vstack(
            rx.heading("AI Decision Support Tool", size="lg", margin_bottom="1em"),
            
            rx.input(
                placeholder="Enter your decision prompt here...",
                on_blur=State.set_prompt,
                style={"margin_bottom": "0.5em"},
                is_disabled=State.is_loading,
            ),
            
            rx.hstack(
                rx.button(
                    "Submit Prompt",
                    on_click=State.handle_submit,
                    is_loading=State.is_loading, # Shows spinner on button
                    is_disabled=State.is_loading,
                    style={"margin_right": "1em"}
                ),
                rx.button(
                    "Refresh Results",
                    on_click=State.fetch_results,
                    is_disabled=rx.cond(State.current_prompt_id.is_none() | State.is_loading, True, False),
                ),
                spacing="1em",
                style={"margin_bottom": "1em"}
            ),
            
            # Display area
            rx.vstack(
                rx.cond(
                    State.error_message != "",
                    rx.box(
                        rx.text(State.error_message, color="red"),
                        padding="0.5em",
                        border="1px solid red",
                        border_radius="md",
                        width="100%",
                        margin_bottom="1em"
                    ),
                    rx.fragment() # Empty fragment if no error
                ),

                rx.text(State.result, margin_bottom="0.5em", font_style="italic"),

                rx.cond(
                    State.summary != "",
                    rx.vstack(
                        rx.heading("Summary:", size="md", margin_top="1em"),
                        rx.text(State.summary, white_space="pre-wrap"), # pre-wrap to respect newlines from LLM
                        align_items="flex-start",
                        width="100%",
                        margin_bottom="1em"
                    ),
                    rx.fragment()
                ),

                rx.cond(
                    State.processed_options.length() > 0, # Check if list is not empty
                    rx.vstack(
                        rx.heading("Processed Options:", size="md", margin_top="1em"),
                        rx.ordered_list(
                            items=State.processed_options, # Directly pass the list
                            render_item=lambda item, index: rx.list_item(rx.text(item)), # Render each item
                        ),
                        align_items="flex-start",
                        width="100%"
                    ),
                    rx.fragment()
                ),
                spacing="0.5em",
                width="100%",
                padding="1em",
                border="1px solid #ddd",
                border_radius="md",
                min_height="200px" # Ensure a minimum height for the results area
            ),
            spacing="1em",
            width="100%"
        ),
        padding="2em",
        max_width="800px", # Constrain width for better readability
        margin="auto" # Center the container
    )

# Add state and page to the app.
app = rx.App(state=State)
app.add_page(index)
# app.compile() # compile() is usually called by reflex CLI, not explicitly here
# For Reflex versions that require explicit compile, ensure it's used appropriately.
# If you are running `reflex run`, this explicit compile() might not be needed or could conflict.
# Typically, `rx.App()` is enough and the CLI handles compilation.
# Let's assume the latest Reflex behavior where explicit compile() in app.py is less common.
# If errors occur, this might be a point to check against Reflex documentation for the specific version.
# For now, commenting it out as it's often handled by the `reflex run` command.
app.compile() # Re-added as per original structure, ensure this matches Reflex version best practice.
