import asyncio
import reflex as rx

class ToastState(rx.State):
    @rx.event
    async def fetch_data(self, message: str, isError: bool = False):
        await asyncio.sleep(1)
        if isError:
            yield rx.toast.error(message)
        else:
            yield rx.toast(message)
