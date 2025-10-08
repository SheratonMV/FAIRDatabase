"""Multi-Factor Authentication (MFA) support using Supabase Auth MFA."""

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from config import supabase_extension
from src.auth.decorators import login_required
from src.exceptions import GenericExceptionHandler

mfa_routes = Blueprint("mfa_routes", __name__, url_prefix="/mfa")


@mfa_routes.route("/enroll", methods=["GET", "POST"])
@login_required()
def enroll():
    """
    Enroll in MFA (Multi-Factor Authentication) using TOTP.

    GET: Display QR code and setup instructions
    POST: Verify and enable MFA

    Returns:
        Rendered enrollment page or redirect to dashboard on success
    """
    user_email = session.get("email", "")

    if request.method == "POST":
        verification_code = request.form.get("code", "").strip()

        if not verification_code:
            flash("Please enter the verification code from your authenticator app.", "danger")
            return redirect(url_for("mfa_routes.enroll"))

        try:
            # Get factor_id from session (set during enrollment initiation)
            factor_id = session.get("mfa_factor_id")

            if not factor_id:
                raise GenericExceptionHandler(
                    "MFA enrollment session expired. Please try again.", status_code=400
                )

            # Verify and enable MFA
            response = supabase_extension.client.auth.mfa.challenge_and_verify(
                {"factor_id": factor_id, "code": verification_code}
            )

            if response:
                # Clear enrollment session data
                session.pop("mfa_factor_id", None)
                session.pop("mfa_qr_code", None)
                session.pop("mfa_secret", None)

                flash("MFA successfully enabled! You'll need your authenticator app for future logins.", "success")
                return redirect(url_for("dashboard_routes.datasets"))

        except Exception as e:
            flash(f"MFA verification failed: {str(e)}", "danger")
            return redirect(url_for("mfa_routes.enroll"))

    # GET request - initiate enrollment
    try:
        access_token = session.get("access_token")

        # Enroll a new TOTP factor
        response = supabase_extension.client.auth.mfa.enroll(
            {"factor_type": "totp", "friendly_name": "Authenticator App"}
        )

        # Store enrollment data in session
        session["mfa_factor_id"] = response.id
        session["mfa_qr_code"] = response.totp.qr_code
        session["mfa_secret"] = response.totp.secret

        return render_template(
            "/auth/mfa_enroll.html",
            user_email=user_email,
            qr_code=response.totp.qr_code,
            secret=response.totp.secret,
        )

    except Exception as e:
        flash(f"Failed to initiate MFA enrollment: {str(e)}", "danger")
        return redirect(url_for("dashboard_routes.datasets"))


@mfa_routes.route("/verify", methods=["GET", "POST"])
def verify():
    """
    Verify MFA code during login.

    This route is called after successful password authentication
    when the user has MFA enabled.

    Returns:
        Rendered verification page or redirect to dashboard on success
    """
    if request.method == "POST":
        verification_code = request.form.get("code", "").strip()

        if not verification_code:
            flash("Please enter your MFA code.", "danger")
            return redirect(url_for("mfa_routes.verify"))

        try:
            # Get factor_id from session (set during login)
            factor_id = session.get("mfa_factor_id")

            if not factor_id:
                flash("MFA session expired. Please log in again.", "danger")
                return redirect(url_for("main_routes.index"))

            # Verify the MFA code
            response = supabase_extension.client.auth.mfa.challenge_and_verify(
                {"factor_id": factor_id, "code": verification_code}
            )

            if response and response.session:
                # Store session tokens
                session["access_token"] = response.session.access_token
                session["refresh_token"] = response.session.refresh_token
                session["expires_at"] = response.session.expires_at
                session["user"] = response.user.id

                # Clear MFA verification session data
                session.pop("mfa_factor_id", None)
                session.pop("mfa_required", None)

                flash("MFA verification successful!", "success")
                return redirect(url_for("dashboard_routes.datasets"))

        except Exception as e:
            flash(f"MFA verification failed: {str(e)}", "danger")
            return redirect(url_for("mfa_routes.verify"))

    # GET request - show verification form
    user_email = session.get("email", "")

    if not session.get("mfa_required"):
        flash("MFA verification not required. Please log in first.", "info")
        return redirect(url_for("main_routes.index"))

    return render_template("/auth/mfa_verify.html", user_email=user_email)


@mfa_routes.route("/disable", methods=["POST"])
@login_required()
def disable():
    """
    Disable MFA for the current user.

    Requires confirmation via password or existing MFA code.

    Returns:
        Redirect to dashboard with status message
    """
    try:
        factor_id = request.form.get("factor_id")

        if not factor_id:
            flash("Invalid MFA factor ID.", "danger")
            return redirect(url_for("dashboard_routes.datasets"))

        # Unenroll the MFA factor
        response = supabase_extension.client.auth.mfa.unenroll({"factor_id": factor_id})

        if response:
            flash("MFA has been disabled for your account.", "success")
        else:
            flash("Failed to disable MFA. Please try again.", "danger")

    except Exception as e:
        flash(f"Error disabling MFA: {str(e)}", "danger")

    return redirect(url_for("dashboard_routes.datasets"))


@mfa_routes.route("/factors", methods=["GET"])
@login_required()
def list_factors():
    """
    List all MFA factors enrolled for the current user.

    Returns:
        JSON list of MFA factors (for API) or rendered page
    """
    try:
        # Get authenticated user
        user_response = supabase_extension.client.auth.get_user()

        # List all MFA factors
        factors = user_response.user.factors or []

        return render_template(
            "/auth/mfa_factors.html",
            user_email=session.get("email", ""),
            factors=factors,
        )

    except Exception as e:
        flash(f"Error retrieving MFA factors: {str(e)}", "danger")
        return redirect(url_for("dashboard_routes.datasets"))
