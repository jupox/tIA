import reflex as rx
from ..state import State

def scheduler_modal() -> rx.Component:
    """UI for creating and editing scheduled jobs, using rx.dialog."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(State.scheduler_modal_title),
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
                            value=str(State.scheduler_prompt_text),
                            on_change=State.set_scheduler_prompt_text,
                            width="100%",
                            rows="5",
                        ),
                        name="scheduler_prompt_text",
                        width="100%",
                    ),
                    rx.form.field(
                        rx.form.label("Iteration"),
                        rx.select(
                            State.iteration_options_values,
                            placeholder="Select iteration type",
                            value=str(State.scheduler_iteration_type),
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
                                "active",
                                "paused",
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
                            icon="circle_alert",
                            color_scheme="red",
                            role="alert",
                            width="100%",
                        ),
                        rx.fragment()
                    ),
                    spacing="3",
                    width="100%",
                ),
                on_submit=State.save_scheduled_job,
                reset_on_submit=False,
                width="100%",
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button("Cancel", variant="soft")
                ),
                rx.button(
                    "Save Job",
                    on_click=State.save_scheduled_job,
                    is_loading=State.scheduler_is_loading
                ),
                spacing="3",
                margin_top="1em",
                justify="end",
            ),
        ),
        open=State.show_scheduler_modal,
        on_open_change=State.set_show_scheduler_modal,
    )

def last_run_details_modal() -> rx.Component:
    """Modal to display the details of the last run."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Last Run Details"),
            rx.cond(
                State.last_run_error_message != "",
                rx.callout(
                    State.last_run_error_message,
                    icon="circle_alert",
                    color_scheme="red",
                    role="alert",
                    margin_bottom="1em",
                ),
                rx.fragment(
                    rx.text(State.last_run_details, width="100%", white_space="pre-wrap")
                )
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button("Close", variant="soft")
                ),
                justify="end",
                margin_top="1em",
            ),
        ),
        open=State.show_last_run_modal,
        on_open_change=State.set_show_last_run_modal,
    )

def scheduled_jobs_table() -> rx.Component:
    """UI table to display scheduled jobs."""
    return rx.box(
        rx.heading("Scheduled Jobs Management", size="5", margin_bottom="1em"),
        rx.hstack(
            rx.button("Load / Refresh Schedules", on_click=State.load_scheduled_jobs, is_loading=State.scheduler_is_loading, size="2"),
            rx.button("Create New Scheduled Job", on_click=lambda: State.open_scheduler_modal(None), size="2"),
            spacing="3",
            margin_bottom="1em",
        ),
        rx.cond(
            State.scheduler_error_message != "",
            rx.callout(
                State.scheduler_error_message,
                icon="circle_alert",
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
                        rx.table.cell(job.get("prompt_text", "")),
                        rx.table.cell(job.get("iteration_type", "N/A")),
                        rx.table.cell(job.get("next_run_at", "N/A")),
                        rx.table.cell(job.get("last_run_at", "N/A")),
                        rx.table.cell(job.get("status", "N/A")),
                        rx.table.cell(job.get("last_run_status", "N/A")),
                        rx.table.cell(
                            rx.hstack(
                                rx.button("Edit", on_click=lambda: State.open_scheduler_modal(job), size="2", variant="outline"),
                                rx.button(
                                    rx.cond(job.get("status") == "active", "Pause", "Resume"),
                                    on_click=lambda: State.toggle_scheduled_job_status(job["id"], job.get("status", "")),
                                    size="2",
                                    variant="outline",
                                ),
                                rx.button("Run Now", on_click=lambda: State.run_scheduled_job_now(job["id"]), size="2", variant="outline"),
                                rx.button("View Last Run",
                                          on_click=State.view_last_run_details(job.get("last_prompt_id")),
                                          size="2",
                                          variant="outline",
                                          is_disabled=job.get("last_prompt_id") is None
                                ),
                                rx.button("Delete", on_click=lambda: State.delete_scheduled_job(job["id"]), color_scheme="red", size="2", variant="solid"),
                                spacing="1",
                            )
                        ),
                    ),
                )
            ),
        ),
        width="100%",
        margin_top="2em",
    )

@rx.page(route="/scheduller", title="tIA Scheduler Management")
def scheduler_page():
    """Scheduler page layout."""
    return rx.container(
        rx.vstack(
            rx.heading("Scheduler Management", size="9"),
            rx.divider(width="100%", margin_y="2em"),
            scheduled_jobs_table(),
            scheduler_modal(),
            last_run_details_modal(),
            spacing="4",
            width="100%",
        ),
        padding="2em",
        max_width="1000px",
        margin="auto",
    )
