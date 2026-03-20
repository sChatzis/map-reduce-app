<<<<<<< HEAD
import requests
import typer
from typing_extensions import Annotated
import os
from pathlib import Path

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/v1/users")  # Assuming router is mounted at /users
TOKEN_FILE = Path.home() / ".mapreduce_token"

app = typer.Typer(help="MapReduce Authentication CLI")
admin_app = typer.Typer(help="System administration commands")
app.add_typer(admin_app, name="admin")


def get_headers():
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        return {"Authorization": f"Bearer {token}"}
    return {}


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
        # Your backend uses a Pydantic TokenRequest, so we send JSON
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
        # Points to GET / to get all users
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
        # Sends PATCH to /{user_id} with UserUpdate payload
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


if __name__ == "__main__":
=======
import requests
import typer
from typing_extensions import Annotated
import os
from pathlib import Path

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/v1/users")  # Assuming router is mounted at /users
TOKEN_FILE = Path.home() / ".mapreduce_token"

app = typer.Typer(help="MapReduce Authentication CLI")
admin_app = typer.Typer(help="System administration commands")
app.add_typer(admin_app, name="admin")


def get_headers():
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        return {"Authorization": f"Bearer {token}"}
    return {}


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
        # Your backend uses a Pydantic TokenRequest, so we send JSON
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
        # Points to GET / to get all users
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
        # Sends PATCH to /{user_id} with UserUpdate payload
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


if __name__ == "__main__":
>>>>>>> ada3ecb (Authentication Service implemented and API integration with UI)
    app()