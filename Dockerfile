# Use Python 3.9 slim image as base
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tk-dev \
        tcl-dev \
        pkg-config \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy game files
COPY game3/ /app/

# Install Python dependencies (if any, though tkinter is built-in)
# For now, just make sure tkinter is available
RUN python -c "import tkinter; print('tkinter is available')"

# Expose display for GUI (when using X11 forwarding)
ENV DISPLAY=:0

# Command to run the game
CMD ["python", "main.py"]