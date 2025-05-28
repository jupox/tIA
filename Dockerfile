# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entrypoint script into the container at /app
COPY entrypoint.sh .

# Make the entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Ensure correct line endings for the entrypoint script (convert CR/LF to LF)
RUN sed -i 's/$//' /app/entrypoint.sh

# Copy the rest of the application
COPY . .

# Expose port 3000 to the outside world
EXPOSE 3000

# Set the entrypoint script to be executed when the container starts
ENTRYPOINT ["/app/entrypoint.sh"]

# Set a default command (will be passed to entrypoint.sh)
CMD ["web"]
