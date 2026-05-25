import requests
import typer
from typing_extensions import Annotated
import os
from pathlib import Path
from jose import jwt

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/v1/users")
MANAGER_URL = os.getenv("MANAGER_URL", "http://localhost:8001/v1")
TOKEN_FILE = Path.home() / ".mapreduce_token"

app = typer.Typer(help="MapReduce Authentication CLI")
admin_app = typer.Typer(help="System administration commands")
jobs_app = typer.Typer(help="Submit and inspect MapReduce jobs")
app.add_typer(admin_app, name="admin")
app.add_typer(jobs_app, name="jobs")


def get_headers():
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        return {"Authorization": f"Bearer {token}"}
    return {}


def get_user_id_from_token() -> int:
    """Decode the locally cached JWT (without signature verification) and
    return the embedded ``user_id``. Exits the CLI if no token is present
    or the payload is malformed."""
    if not TOKEN_FILE.exists():
        typer.echo("Not logged in. Run `cli.py login` first.")
        raise typer.Exit(code=1)
    token = TOKEN_FILE.read_text().strip()
    try:
        claims = jwt.get_unverified_claims(token)
    except Exception as e:
        typer.echo(f"Could not decode token: {e}")
        raise typer.Exit(code=1)
    user_id = claims.get("user_id")
    if user_id is None:
        typer.echo("Token payload missing user_id. Log in again.")
        raise typer.Exit(code=1)
    return int(user_id)


# ==========================================
# Authentication
# ==========================================
@app.command()
def signup(
        username: Annotated[str, typer.Option(prompt=True, help="Choose a username")],
        password: Annotated[str, typer.Option(prompt=True, hide_input=True, help="Choose a password")]
):
    """Create a new user account."""
    try:
        response = requests.post(f"{BASE_URL}/signup", json={"username": username, "password": password})
        if response.status_code == 201:
            typer.echo("User created successfully. Status: PENDING_APPROVAL. Wait for admin.")
        else:
            typer.echo(f"Error: {response.json().get('detail', response.text)}")
    except Exception as e:
        typer.echo(f"Connection Error: {e}")


@app.command()
def login(
        username: Annotated[str, typer.Option(prompt=True, help="Your username")],
        password: Annotated[str, typer.Option(prompt=True, hide_input=True, help="Your password")]
):
    """Authenticate to receive a user token."""
    try:
        response = requests.post(f"{BASE_URL}/login", json={"username": username, "password": password})
        if response.status_code == 200:
            token = response.json().get("access_token")
            TOKEN_FILE.write_text(token)
            typer.echo("Login successful. Token saved locally.")
        else:
            typer.echo(f"Login failed: {response.json().get('detail', 'Unknown error')}")
    except Exception as e:
        typer.echo(f"Error: {e}")


@app.command()
def whoami():
    """Check current logged-in user info."""
    try:
        response = requests.get(f"{BASE_URL}/me", headers=get_headers())
        if response.status_code == 200:
            user = response.json()
            typer.echo(f"Logged in as: {user.get('username')} | Role: {user.get('role')}")
        else:
            typer.echo("Not logged in or token expired.")
    except Exception as e:
        typer.echo(f"Error: {e}")


# ==========================================
# Admin Commands (Requires Admin JWT)
# ==========================================
@admin_app.command("list-users")
def admin_list_users():
    """List all registered users (Admin only)."""
    try:
        response = requests.get(f"{BASE_URL}/", headers=get_headers())
        response.raise_for_status()

        users = response.json()
        if not users:
            typer.echo("No users found.")
            return

        typer.echo(f"{'ID':<5} | {'Username':<15} | {'Role':<10} | {'Status'}")
        typer.echo("-" * 50)
        for u in users:
            typer.echo(f"{u['id']:<5} | {u['username']:<15} | {u['role']:<10} | {u['status']}")

    except requests.exceptions.HTTPError as e:
        typer.echo(f"API Error: {e.response.json().get('detail', e)}")
    except Exception as e:
        typer.echo(f"Error: {e}")


@admin_app.command("verify-user")
def admin_verify_user(
        user_id: Annotated[int, typer.Argument(help="ID of the user to verify")]
):
    """Verify or approve a user account."""
    try:
        payload = {"status": "ACTIVE"}
        response = requests.patch(f"{BASE_URL}/{user_id}", json=payload, headers=get_headers())
        response.raise_for_status()
        typer.echo(f"User ID {user_id} is now ACTIVE.")
    except requests.exceptions.HTTPError as e:
        typer.echo(f"API Error: {e.response.json().get('detail', e)}")
    except Exception as e:
        typer.echo(f"Error: {e}")


@admin_app.command("delete-user")
def admin_delete_user(
        user_id: Annotated[int, typer.Argument(help="ID of the user to delete")]
):
    """Delete a user from the system."""
    if typer.confirm(f"Are you sure you want to delete User ID {user_id}?"):
        try:
            response = requests.delete(f"{BASE_URL}/{user_id}", headers=get_headers())
            response.raise_for_status()
            typer.echo(f"User ID {user_id} deleted successfully.")
        except requests.exceptions.HTTPError as e:
            typer.echo(f"API Error: {e.response.json().get('detail', e)}")
        except Exception as e:
            typer.echo(f"Error: {e}")


# ==========================================
# Jobs Commands
# ==========================================
@jobs_app.command("submit")
def jobs_submit(
        input_file: Annotated[str, typer.Option("--input", help="MinIO key of the input file")],
        mapper: Annotated[str, typer.Option("--mapper", help="MinIO key of the mapper script")],
        reducer: Annotated[str, typer.Option("--reducer", help="MinIO key of the reducer script")],
        output: Annotated[str, typer.Option("--output", help="MinIO key for the final output (optional)")] = "",
        mappers: Annotated[int, typer.Option("--mappers", help="Number of map tasks")] = 4,
        reducers: Annotated[int, typer.Option("--reducers", help="Number of reduce tasks")] = 2,
):
    """Submit a new MapReduce job to the manager."""
    user_id = get_user_id_from_token()
    payload = {
        "input_files": input_file,
        "output_path": output,
        "mapper_code": mapper,
        "reducer_code": reducer,
        "user_id": user_id,
        "num_mappers": mappers,
        "num_reducers": reducers,
    }
    try:
        response = requests.post(f"{MANAGER_URL}/jobs", json=payload, headers=get_headers())
        response.raise_for_status()
        job = response.json()
        typer.echo(f"Job created: {job['job_id']} (status: {job['status']})")
    except requests.exceptions.HTTPError as e:
        typer.echo(f"API Error: {e.response.json().get('detail', e)}")
    except Exception as e:
        typer.echo(f"Error: {e}")


@jobs_app.command("status")
def jobs_status(
        job_id: Annotated[str, typer.Argument(help="UUID of the job to inspect")]
):
    """Show the current status of a single job."""
    try:
        response = requests.get(f"{MANAGER_URL}/jobs/{job_id}", headers=get_headers())
        response.raise_for_status()
        job = response.json()
        typer.echo(
            f"Job {job['job_id']}\n"
            f"  status:    {job['status']}\n"
            f"  mappers:   {job['num_mappers']}\n"
            f"  reducers:  {job['num_reducers']}\n"
            f"  input:     {job['input_files']}\n"
            f"  output:    {job['output_path']}\n"
            f"  created:   {job['created_at']}\n"
            f"  updated:   {job['updated_at']}"
        )
    except requests.exceptions.HTTPError as e:
        typer.echo(f"API Error: {e.response.json().get('detail', e)}")
    except Exception as e:
        typer.echo(f"Error: {e}")


@jobs_app.command("list")
def jobs_list():
    """List all jobs known to the manager."""
    try:
        response = requests.get(f"{MANAGER_URL}/jobs", headers=get_headers())
        response.raise_for_status()
        jobs = response.json()
        if not jobs:
            typer.echo("No jobs found.")
            return

        typer.echo(f"{'Job ID':<38} | {'Status':<12} | {'Map':<4} | {'Red':<4} | Created")
        typer.echo("-" * 90)
        for j in jobs:
            typer.echo(
                f"{j['job_id']:<38} | "
                f"{j['status']:<12} | "
                f"{j['num_mappers']:<4} | "
                f"{j['num_reducers']:<4} | "
                f"{j['created_at']}"
            )
    except requests.exceptions.HTTPError as e:
        typer.echo(f"API Error: {e.response.json().get('detail', e)}")
    except Exception as e:
        typer.echo(f"Error: {e}")


@jobs_app.command("result")
def jobs_result(
        job_id: Annotated[str, typer.Argument(help="UUID of the completed job")]
):
    """Fetch the output path of a completed job."""
    try:
        response = requests.get(f"{MANAGER_URL}/jobs/{job_id}/result", headers=get_headers())
        response.raise_for_status()
        body = response.json()
        typer.echo(f"Output: {body['output_path']}")
    except requests.exceptions.HTTPError as e:
        typer.echo(f"API Error: {e.response.json().get('detail', e)}")
    except Exception as e:
        typer.echo(f"Error: {e}")


if __name__ == "__main__":
    app()
