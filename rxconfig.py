import reflex as rx

config = rx.Config(
    app_name="app",
    api_url="http://0.0.0.0:8000",
    plugins=[rx.plugins.TailwindV3Plugin()],
)