"""
CARES Project Service
Single gateway for all project leadership/volunteer assignment changes.

Nothing should create, end, or otherwise mutate a ProjectAssignment row
except through the functions in this module. Routing all assignment
changes through here keeps history consistent (at most one open-ended
assignment per member+project+role at a time) and gives every
appointment, resignation, dismissal, term-completion and annual restart
a single, auditable code path -- mirroring how services/journal_service.py
is the single gateway for GL postings.
"""

from datetime import date

from models import db, Project, ProjectAssignment, PROJECT_ASSIGNMENT_END_REASONS


class ProjectServiceError(Exception):
    """Raised when a project assignment/lifecycle action cannot be completed."""
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_open_assignment(project_id, member_id, role):
    return ProjectAssignment.query.filter_by(
        project_id=project_id, member_id=member_id, role=role, end_date=None
    ).first()


# ---------------------------------------------------------------------------
# Single-assignment lifecycle
# ---------------------------------------------------------------------------

def assign_member(project, member, role, assigned_by=None, start_date=None):
    """Appoint a member as a Leader or Volunteer on a project.

    Idempotent: if the member already has an open assignment in that role
    on this project, the existing assignment is returned unchanged rather
    than creating a duplicate.
    """
    if role not in ('Leader', 'Volunteer'):
        raise ProjectServiceError(f"Invalid role '{role}'. Must be 'Leader' or 'Volunteer'.")

    if member.organization_id != project.organization_id:
        raise ProjectServiceError(
            "Member and project belong to different organizations."
        )

    existing = _get_open_assignment(project.id, member.id, role)
    if existing:
        return existing

    assignment = ProjectAssignment(
        project_id=project.id,
        member_id=member.id,
        role=role,
        start_date=start_date or date.today(),
        assigned_by=assigned_by,
    )
    db.session.add(assignment)
    db.session.commit()
    return assignment


def end_assignment(assignment, end_reason, ended_by=None, end_notes=None, end_date=None):
    """Close out a single assignment: resignation, dismissal, replacement, etc.

    This is the only way an assignment's end_date/end_reason should be set.
    """
    if end_reason not in PROJECT_ASSIGNMENT_END_REASONS:
        raise ProjectServiceError(
            f"Invalid end_reason '{end_reason}'. Must be one of {PROJECT_ASSIGNMENT_END_REASONS}."
        )
    if assignment.end_date is not None:
        raise ProjectServiceError("This assignment has already ended.")

    assignment.end_date = end_date or date.today()
    assignment.end_reason = end_reason
    assignment.end_notes = end_notes
    assignment.ended_by = ended_by
    db.session.commit()
    return assignment


def replace_leader(project, outgoing_member, incoming_member, ended_by=None, end_notes=None):
    """Convenience wrapper for the common case of swapping one leader for
    another mid-term: ends the outgoing leader's assignment as 'Replaced'
    and appoints the incoming leader in a single call.
    """
    outgoing = _get_open_assignment(project.id, outgoing_member.id, 'Leader')
    if not outgoing:
        raise ProjectServiceError(
            f"{outgoing_member.name} is not currently a leader on this project."
        )
    end_assignment(outgoing, end_reason='Replaced', ended_by=ended_by, end_notes=end_notes)
    return assign_member(project, incoming_member, role='Leader', assigned_by=ended_by)


# ---------------------------------------------------------------------------
# Whole-project lifecycle
# ---------------------------------------------------------------------------

def close_project_for_year(project, ended_by=None, end_notes=None):
    """End every currently-open assignment on a project (the year's cycle is
    over) and mark the project itself Completed.

    This does not create next year's project -- see restart_project() for
    that step, which is a deliberate, separate action.
    """
    for assignment in project.active_assignments:
        end_assignment(
            assignment, end_reason='Term Completed', ended_by=ended_by, end_notes=end_notes
        )
    project.status = 'Completed'
    db.session.commit()
    return project


def restart_project(project, start_date=None, carry_forward_people=True, created_by=None):
    """Start next year's iteration of a recurring project.

    Creates a brand-new Project row linked back to this one via
    previous_project_id, rather than mutating this Project in place. That
    keeps this year's budget, journal entries, and assignment history
    exactly as they were, and gives the new year a clean assignment history
    of its own -- while still being able to walk the chain of a project's
    full multi-year history via previous_project / next_project.
    """
    if project.next_project is not None:
        raise ProjectServiceError(
            f"'{project.name}' already has a follow-on project for the next cycle."
        )

    new_project = Project(
        name=project.name,
        description=project.description,
        start_date=start_date or date.today(),
        end_date=None,
        status='Active',
        budget=project.budget,
        organization_id=project.organization_id,
        previous_project=project,
    )
    db.session.add(new_project)
    db.session.flush()  # assign new_project.id before creating assignments

    if carry_forward_people:
        # Only members whose term ended because the year completed normally
        # are carried forward automatically -- someone who resigned or was
        # dismissed mid-year does not silently reappear next year.
        completed = [
            a for a in project.assignments.filter(
                ProjectAssignment.end_reason == 'Term Completed'
            ).all()
        ]
        seen = set()
        for a in completed:
            key = (a.member_id, a.role)
            if key in seen:
                continue
            seen.add(key)
            assign_member(
                new_project, a.member, role=a.role,
                assigned_by=created_by, start_date=new_project.start_date
            )

    db.session.commit()
    return new_project
