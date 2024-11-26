# Use the recommended Python image
FROM python:slim-bullseye

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Define the command to run your script
CMD ["python", "soleless_standalone.py"]

