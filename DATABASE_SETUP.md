# Database Setup Guide

## Overview

The TeenCivics application uses a PostgreSQL database to store all its data. This guide provides instructions for setting up the database connection, which is required for the application to run correctly.

## Production Environment (Railway)

The production application is hosted on Railway, which automatically provides and configures the PostgreSQL database. Railway injects the `DATABASE_URL` environment variable into the application's environment, so no manual configuration is required for the deployed application.

## Local Development Environment

For local development, you will need to connect to a PostgreSQL database. You can either use a local PostgreSQL instance or a cloud-hosted database (including a free tier from Railway).

### Connecting to a Railway Database

1.  **Create a PostgreSQL Database on Railway:**
    *   Go to your Railway project dashboard.
    *   Add a new service and select "PostgreSQL."

2.  **Get the Connection String:**
    *   Once the database is provisioned, navigate to the PostgreSQL service in your Railway dashboard.
    *   Go to the "Connect" tab.
    *   Copy the "Postgres Connection URL."

3.  **Configure your `.env` file:**
    *   Create a file named `.env` in the root of the project if it doesn't already exist.
    *   Add the following line to your `.env` file, replacing `<your-connection-url>` with the URL you copied from Railway:
        ```
        DATABASE_URL=<your-connection-url>
        ```

### Initializing the Database

After setting up your `DATABASE_URL`, you need to initialize the database schema. Run the following command from the root of the project:

```bash
python3 -c "from src.database.connection import init_db_tables; init_db_tables()"
```

This command will create all the necessary tables and indexes in your database.

## Testing the Connection

To verify that your database connection is configured correctly, you can run the `ping_database.py` script:

```bash
python3 scripts/ping_database.py
```

If the connection is successful, you will see a "Database connection successful!" message. If it fails, the script will provide an error message to help you diagnose the issue.