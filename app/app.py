from app.pages.scheduler import scheduler_page
from app.states.toast import ToastState
import reflex as rx
from .state import State

def prompt_form() -> rx.Component:
    """Form for entering and saving a new prompt."""
    return rx.box(
        rx.heading("Submit a New Prompt", size="5", margin_bottom="1em"),
        rx.hstack(   
            rx.text_area(
                placeholder="Enter your prompt here...",
                value=State.prompt,
                on_change=State.set_prompt,
                width="100%",
                margin_bottom="1em",
                rows="5",
                resize="vertical"
            ),
        ),
        rx.hstack(  
            rx.spacer(),          
            rx.button(
                "Save Prompt",
                on_click=State.save_prompt,
                is_disabled=State.prompt.strip() == "",
                size="2",
            ),
            rx.button(
                "Load Prompts",
                on_click=State.load_prompts,
                size="2",
            ),
            rx.button(
                "Archived Prompts",
                on_click=State.set_show_archived_modal(True),
                size="2",
            ),
            rx.button(
                "Scheduller",
                on_click=rx.redirect(
                    "/scheduller"
                ),
                size="2",
            ),
            spacing="3",
            align="end",
            width="100%",
        ),
        margin_bottom="2em",
    )

def prompts_table() -> rx.Component:
    """Table to display all prompts with actions."""
    return rx.box(
        rx.heading("Prompts Table", size="5", margin_bottom="1em"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Job ID"),
                    rx.table.column_header_cell("Prompt Text"),
                    rx.table.column_header_cell("Status"),
                    rx.table.column_header_cell("Actions"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    State.prompts,
                    lambda prompt: rx.table.row(
                        rx.table.cell(prompt["id"]),
                        rx.table.cell(prompt["prompt_text"]),
                        rx.table.cell(prompt["status"]),
                        rx.table.cell(
                            rx.hstack(
                                rx.button(
                                    rx.icon("play", size=18),
                                    on_click=State.resend_prompt(prompt["id"]),
                                    size="1",
                                ),
                                rx.button(
                                    rx.icon("refresh_ccw", size=18),
                                    on_click=State.refresh_status(prompt["id"]),
                                    size="1",
                                ),
                                rx.button(
                                    rx.icon("archive", size=18),
                                    color_scheme="red",
                                    on_click=State.archive_prompt(prompt["id"]),
                                    size="1",
                                ),
                                spacing="2",
                            )
                        ),
                    ),
                )
            ),
        ),
        margin_bottom="2em",
    )

def archived_prompts_modal() -> rx.Component:
    """Modal to display archived prompts with actions."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Archived Prompts"),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("ID"),
                        rx.table.column_header_cell("Prompt Text"),
                        rx.table.column_header_cell("Archived At"),
                        rx.table.column_header_cell("Actions"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        State.archived_prompts,
                        lambda archived: rx.table.row(
                            rx.table.cell(archived["id"]),
                            rx.table.cell(archived["prompt_text"]),
                            rx.table.cell(archived["archived_at"]),
                            rx.table.cell(
                                rx.hstack(
                                    rx.button(
                                        "Restore",
                                        on_click=lambda: State.restore_prompt(archived["id"]),
                                        size="1",
                                    ),
                                    rx.button(
                                        "Delete",
                                        color_scheme="red",
                                        on_click=lambda: State.delete_archived_prompt(archived["id"]),
                                        size="1",
                                    ),
                                    spacing="2",
                                )
                            ),
                        ),
                    )
                ),
            ),
            rx.cond(
                State.archived_error_message != "",
                rx.callout(
                    State.archived_error_message,
                    icon="circle_alert",
                    color_scheme="red",
                    role="alert",
                    margin_top="1em",
                ),
                rx.fragment(),
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button("Close", variant="soft")
                ),
                justify="end",
                margin_top="1em",
            ),
        ),
        open=State.show_archived_modal,
        on_open_change=State.set_show_archived_modal,
    )

@rx.page(title="AI Decision Support", on_load=State.load_prompts)
def index():
    """Main page layout."""
    return rx.container(
        rx.vstack(
            rx.heading("AI Decision Support Tool Task", size="9"),
            rx.heading("Task IA - TIA", size="6", margin_bottom="1em"),
            prompt_form(),
            prompts_table(),
            archived_prompts_modal(),
            spacing="4",
            width="100%",
        ),
        padding="2em",
        max_width="1000px",
        margin="auto",
    )

# Add state and pages to the app.
app = rx.App()
app.add_page(scheduler_page)  
