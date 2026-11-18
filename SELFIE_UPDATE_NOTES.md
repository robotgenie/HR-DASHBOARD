# Live Selfie Update

Implemented for Employee/Intern accounts:

- Live camera selfie is required during sign-in.
- Live camera selfie is required during sign-out.
- Selfies are captured from the browser camera; existing image upload is not used for this flow.
- Login/logout selfie files are stored under backend `uploads/selfies/` with unique server-generated names.
- Each work session stores `login_selfie_path` and `logout_selfie_path`.
- HR/Admin login/logout remains unchanged.
- A new Alembic migration adds the selfie path columns.
- If camera permission is denied/cancelled, the employee/intern is not signed in/out.
- Existing login/session, audit and logout flows remain in place and are extended with selfie metadata.

Migration:
`e8f9a0b1c2d3_add_work_session_selfies.py`
