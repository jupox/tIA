#!/bin/sh
set -e # Exit immediately if a command exits with a non-zero status.

# The first argument to this script will determine what to run.
case "$1" in
    web)
        echo "Starting Reflex web server..."
        # Initialize if .reflex directory is missing, useful for first run in volume
        # reflex init 
        # Ensure frontend is built before running, though `reflex run` usually handles this.
        # reflex export --quiet
        
        # Add /home/swebot/.local/bin to PATH if it's not already there
        # This is important because reflex and other Python tools might be installed there
        # when pip install --user is used (common in some environments or if site-packages isn't writable)
        if ! echo "$PATH" | grep -q "/home/swebot/.local/bin"; then
            export PATH="$PATH:/home/swebot/.local/bin"
        fi

        pip install --upgrade pip
        pip install --user reflex --upgrade

        exec reflex run --env prod
        ;;
    worker)
        echo "Starting Celery worker..."
        
        if ! echo "$PATH" | grep -q "/home/swebot/.local/bin"; then
            export PATH="$PATH:/home/swebot/.local/bin"
        fi
        
        exec celery -A app.celery_app worker -l info
        ;;
    *)
        # If no argument or an unknown argument is given, execute the passed command.
        # This allows for running arbitrary commands like `sh` for debugging.
        exec "$@"
        ;;
esac