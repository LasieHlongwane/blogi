import os

from datetime import datetime, timezone, timedelta

import click
from flask.cli import with_appcontext

from extensions import db
from models import (
    AdminUser,
    CreatorAccount,
    CreatorProfile,
    ContentCategory,
    ContentPost,
    ContentMedia,
    EmailSubscriber,
)


# ============================================================
# HELPERS
# ============================================================


def utc_now():
    return datetime.now(timezone.utc)


def create_post(
    *,
    title,
    slug,
    excerpt,
    body,
    content_type,
    category,
    creator_account=None,
    access_level="public",
    is_featured=False,
    days_ago=0,
    cover_image_url=None,
):
    """
    Create and return a published development post.
    """

    published_at = utc_now() - timedelta(
        days=days_ago
    )

    post = ContentPost(
        creator_account=creator_account,
        title=title,
        slug=slug,
        excerpt=excerpt,
        body=body,
        content_type=content_type,
        access_level=access_level,
        status="published",
        is_featured=is_featured,
        published_at=published_at,
        cover_image_url=cover_image_url,
        category=category,
    )

    db.session.add(post)

    return post


# ============================================================
# PRODUCTION IDENTITY INITIALIZATION
# ============================================================


def initialize_production_identity():
    """
    Create the initial production AdminUser and legacy
    CreatorProfile from environment variables.

    Existing records are never overwritten.

    This function intentionally does NOT automatically create
    or backfill CreatorAccount records.

    The creator-account backfill is performed explicitly with:

        python -m flask --app app backfill-creator-account

    This keeps application startup safe and prevents accidental
    ownership changes every time Render starts the application.
    """

    result = {
        "admin_created": False,
        "creator_created": False,
        "admin_configured": False,
        "creator_configured": False,
    }

    # ========================================================
    # ADMIN ENVIRONMENT VARIABLES
    # ========================================================

    admin_username = (
        os.getenv(
            "ADMIN_USERNAME",
            "",
        )
        .strip()
    )

    admin_email = (
        os.getenv(
            "ADMIN_EMAIL",
            "",
        )
        .strip()
        .lower()
    )

    admin_password = os.getenv(
        "ADMIN_PASSWORD",
        "",
    )

    # ========================================================
    # CREATOR ENVIRONMENT VARIABLES
    # ========================================================

    creator_name = (
        os.getenv(
            "CREATOR_NAME",
            "",
        )
        .strip()
    )

    creator_username = (
        os.getenv(
            "CREATOR_USERNAME",
            "",
        )
        .strip()
        .lower()
    )

    # ========================================================
    # ADMIN
    # ========================================================

    if (
        admin_username
        and admin_email
        and admin_password
    ):

        result["admin_configured"] = True

        existing_admin = (
            AdminUser.query
            .filter_by(
                username=admin_username
            )
            .first()
        )

        existing_admin_email = (
            AdminUser.query
            .filter_by(
                email=admin_email
            )
            .first()
        )

        if (
            existing_admin is None
            and existing_admin_email is None
        ):

            admin = AdminUser(
                username=admin_username,
                email=admin_email,
                is_active=True,
            )

            admin.set_password(
                admin_password
            )

            db.session.add(
                admin
            )

            result["admin_created"] = True

    # ========================================================
    # LEGACY CREATOR PROFILE
    # ========================================================

    if (
        creator_name
        and creator_username
    ):

        result["creator_configured"] = True

        existing_creator = (
            CreatorProfile.query
            .filter_by(
                username=creator_username
            )
            .first()
        )

        if existing_creator is None:

            creator = CreatorProfile(
                display_name=creator_name,
                username=creator_username,
                tagline="",
                bio="",
                profile_image_url=None,
                intro_reel_url=None,
                instagram_url=None,
                tiktok_url=None,
                youtube_url=None,
            )

            db.session.add(
                creator
            )

            result["creator_created"] = True

    # ========================================================
    # SAVE
    # ========================================================

    if (
        result["admin_created"]
        or result["creator_created"]
    ):

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            raise

    return result


# ============================================================
# CREATE ADMIN CLI COMMAND
# ============================================================


@click.command(
    "create-admin"
)
@with_appcontext
def create_admin_command():
    """
    Create the production admin and legacy creator profile
    using environment variables.

    Usage:

        python -m flask --app app create-admin
    """

    click.echo("")
    click.echo(
        "========================================"
    )
    click.echo(
        " Creator Platform Production Setup"
    )
    click.echo(
        "========================================"
    )
    click.echo("")

    result = (
        initialize_production_identity()
    )

    # ========================================================
    # ADMIN RESULT
    # ========================================================

    if not result["admin_configured"]:

        click.echo(
            "Admin not created."
        )

        click.echo(
            "Set ADMIN_USERNAME, ADMIN_EMAIL "
            "and ADMIN_PASSWORD."
        )

    elif result["admin_created"]:

        click.echo(
            "Production admin created successfully."
        )

    else:

        click.echo(
            "Admin already exists. No changes made."
        )

    # ========================================================
    # CREATOR RESULT
    # ========================================================

    if not result["creator_configured"]:

        click.echo(
            "Creator profile not created."
        )

        click.echo(
            "Set CREATOR_NAME and CREATOR_USERNAME."
        )

    elif result["creator_created"]:

        click.echo(
            "Creator profile created successfully."
        )

    else:

        click.echo(
            "Creator profile already exists. "
            "No changes made."
        )

    click.echo("")


# ============================================================
# BACKFILL EXISTING CREATOR ACCOUNT
# ============================================================


@click.command(
    "backfill-creator-account"
)
@with_appcontext
def backfill_creator_account_command():
    """
    Connect the existing single-creator production data to the
    new CreatorAccount SaaS tenant.

    This command is designed for the existing creator blog that
    existed before CreatorAccount was introduced.

    It does NOT delete posts, folders, comments, subscribers,
    media or the existing CreatorProfile.

    Usage:

        python -m flask --app app backfill-creator-account
    """

    click.echo("")
    click.echo(
        "========================================"
    )
    click.echo(
        " Creator Account Backfill"
    )
    click.echo(
        "========================================"
    )
    click.echo("")

    # ========================================================
    # FIND EXISTING PROFILE
    # ========================================================

    creator = (
        CreatorProfile.query
        .order_by(
            CreatorProfile.id.asc()
        )
        .first()
    )

    if not creator:

        click.echo(
            "No existing CreatorProfile was found."
        )

        click.echo(
            "Nothing was changed."
        )

        click.echo("")

        return

    click.echo(
        f"Existing creator: "
        f"{creator.display_name} "
        f"(@{creator.username})"
    )

    # ========================================================
    # ALREADY BACKFILLED
    # ========================================================

    if creator.creator_account_id:

        account = db.session.get(
            CreatorAccount,
            creator.creator_account_id,
        )

        click.echo("")
        click.echo(
            "This creator profile is already connected "
            "to a CreatorAccount."
        )

        if account:

            click.echo(
                f"CreatorAccount ID: {account.id}"
            )

            click.echo(
                f"Username: @{account.username}"
            )

        click.echo("")
        click.echo(
            "No duplicate account was created."
        )

        click.echo("")

        return

    # ========================================================
    # ACCOUNT USERNAME
    # ========================================================

    account_username = (
        creator.username
        .strip()
        .lower()
    )

    # ========================================================
    # ACCOUNT EMAIL
    # ========================================================
    #
    # Prefer CREATOR_EMAIL.
    #
    # If it is not configured, ADMIN_EMAIL is used for the
    # existing legacy creator only.
    #
    # Future creator registrations will provide their own
    # creator email address.
    # ========================================================

    creator_email = (
        os.getenv(
            "CREATOR_EMAIL",
            "",
        )
        .strip()
        .lower()
    )

    if not creator_email:

        creator_email = (
            os.getenv(
                "ADMIN_EMAIL",
                "",
            )
            .strip()
            .lower()
        )

    if not creator_email:

        click.echo("")
        click.echo(
            "Backfill stopped."
        )

        click.echo(
            "Set CREATOR_EMAIL in the environment."
        )

        click.echo(
            "For the existing creator only, ADMIN_EMAIL "
            "can also be used as the fallback."
        )

        click.echo("")

        return

    # ========================================================
    # FIND EXISTING ACCOUNT
    # ========================================================

    account = (
        CreatorAccount.query
        .filter(
            db.or_(
                db.func.lower(
                    CreatorAccount.username
                )
                == account_username,

                db.func.lower(
                    CreatorAccount.email
                )
                == creator_email,
            )
        )
        .first()
    )

    account_created = False

    # ========================================================
    # CREATE ACCOUNT IF NECESSARY
    # ========================================================

    if account is None:

        # ----------------------------------------------------
        # PASSWORD
        # ----------------------------------------------------
        #
        # Existing production creator previously used the
        # AdminUser login.
        #
        # For the first creator account we can use
        # CREATOR_PASSWORD when configured.
        #
        # Otherwise ADMIN_PASSWORD is used only for this
        # one-time legacy migration.
        # ----------------------------------------------------

        creator_password = os.getenv(
            "CREATOR_PASSWORD",
            "",
        )

        if not creator_password:

            creator_password = os.getenv(
                "ADMIN_PASSWORD",
                "",
            )

        if not creator_password:

            click.echo("")
            click.echo(
                "Backfill stopped."
            )

            click.echo(
                "Set CREATOR_PASSWORD in the environment."
            )

            click.echo(
                "ADMIN_PASSWORD may be used as the "
                "legacy fallback."
            )

            click.echo("")

            return

        account = CreatorAccount(
            username=account_username,
            email=creator_email,

            # Existing creator is already approved.
            account_status="active",

            # This is a migration of the original creator,
            # not a new paid registration.
            payment_status="paid",
            registration_paid_at=utc_now(),

            approved_at=utc_now(),

            # Keep the existing creator operational while
            # SaaS billing is introduced later.
            subscription_status="active",
            subscription_started_at=utc_now(),
            subscription_expires_at=None,
        )

        account.set_password(
            creator_password
        )

        db.session.add(
            account
        )

        db.session.flush()

        account_created = True

        click.echo("")
        click.echo(
            "Created CreatorAccount."
        )

    else:

        click.echo("")
        click.echo(
            "Existing CreatorAccount found."
        )

    # ========================================================
    # ASSIGN PROFILE
    # ========================================================

    creator.creator_account_id = (
        account.id
    )

    # ========================================================
    # ASSIGN CATEGORIES
    # ========================================================

    categories_updated = (
        ContentCategory.query
        .filter(
            ContentCategory.creator_account_id
            .is_(None)
        )
        .update(
            {
                ContentCategory.creator_account_id:
                    account.id
            },
            synchronize_session=False,
        )
    )

    # ========================================================
    # ASSIGN POSTS
    # ========================================================

    posts_updated = (
        ContentPost.query
        .filter(
            ContentPost.creator_account_id
            .is_(None)
        )
        .update(
            {
                ContentPost.creator_account_id:
                    account.id
            },
            synchronize_session=False,
        )
    )

    # ========================================================
    # ASSIGN NEWSLETTER SUBSCRIBERS
    # ========================================================

    subscribers_updated = (
        EmailSubscriber.query
        .filter(
            EmailSubscriber.creator_account_id
            .is_(None)
        )
        .update(
            {
                EmailSubscriber.creator_account_id:
                    account.id
            },
            synchronize_session=False,
        )
    )

    # ========================================================
    # SAVE
    # ========================================================

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        click.echo("")
        click.echo(
            "Backfill failed. Database changes "
            "were rolled back."
        )

        raise

    # ========================================================
    # RESULT
    # ========================================================

    click.echo("")
    click.echo(
        "========================================"
    )
    click.echo(
        " Backfill completed successfully"
    )
    click.echo(
        "========================================"
    )
    click.echo("")

    click.echo(
        f"CreatorAccount ID: {account.id}"
    )

    click.echo(
        f"Username: @{account.username}"
    )

    click.echo(
        f"Email: {account.email}"
    )

    click.echo(
        f"Account created: "
        f"{'yes' if account_created else 'no'}"
    )

    click.echo(
        f"Profile connected: yes"
    )

    click.echo(
        f"Folders connected: "
        f"{categories_updated}"
    )

    click.echo(
        f"Posts connected: "
        f"{posts_updated}"
    )

    click.echo(
        f"Subscribers connected: "
        f"{subscribers_updated}"
    )

    click.echo("")


# ============================================================
# DEVELOPMENT SEED COMMAND
# ============================================================


@click.command(
    "seed"
)
@click.option(
    "--reset",
    is_flag=True,
    help=(
        "Delete existing development data "
        "before seeding."
    ),
)
@with_appcontext
def seed_command(reset):
    """
    Seed the application with DEVELOPMENT content.

    Do not use this command against the production database.

    Usage:

        python -m flask --app app seed

    Reset and seed:

        python -m flask --app app seed --reset
    """

    click.echo("")
    click.echo(
        "========================================"
    )
    click.echo(
        " Creator Platform Development Seed"
    )
    click.echo(
        "========================================"
    )
    click.echo("")

    # ========================================================
    # OPTIONAL RESET
    # ========================================================

    if reset:

        click.echo(
            "Resetting existing development data..."
        )

        ContentMedia.query.delete()
        ContentPost.query.delete()
        ContentCategory.query.delete()
        EmailSubscriber.query.delete()
        CreatorProfile.query.delete()
        CreatorAccount.query.delete()

        db.session.commit()

        click.echo(
            "Existing development data removed."
        )

        click.echo("")

    # ========================================================
    # PROTECT AGAINST DUPLICATE SEEDING
    # ========================================================

    existing_creator = (
        CreatorProfile.query.first()
    )

    if existing_creator:

        click.echo(
            "Seed skipped: a creator profile "
            "already exists."
        )

        click.echo("")

        click.echo(
            "WARNING: Do not use --reset against "
            "your production Neon database."
        )

        click.echo("")

        return

    # ========================================================
    # ADMIN USER
    # ========================================================

    click.echo(
        "Creating development admin account..."
    )

    existing_admin = (
        AdminUser.query
        .filter_by(
            username="naledi"
        )
        .first()
    )

    if existing_admin is None:

        admin = AdminUser(
            username="naledi",
            email="naledi@example.com",
            is_active=True,
        )

        admin.set_password(
            "Creator123!"
        )

        db.session.add(
            admin
        )

    # ========================================================
    # CREATOR ACCOUNT
    # ========================================================

    click.echo(
        "Creating development creator account..."
    )

    creator_account = CreatorAccount(
        username="naledi",
        email="creator@example.com",
        account_status="active",
        payment_status="paid",
        registration_paid_at=utc_now(),
        approved_at=utc_now(),
        subscription_status="active",
        subscription_started_at=utc_now(),
        subscription_expires_at=None,
    )

    creator_account.set_password(
        "Creator123!"
    )

    db.session.add(
        creator_account
    )

    db.session.flush()

    # ========================================================
    # CREATOR PROFILE
    # ========================================================

    click.echo(
        "Creating creator profile..."
    )

    creator = CreatorProfile(
        creator_account_id=(
            creator_account.id
        ),
        display_name="Naledi M.",
        username="naledi",
        tagline=(
            "Life, conversations, beautiful moments "
            "and everything in between."
        ),
        bio=(
            "Welcome to my little corner of the internet. "
            "This is where I share stories from my life, "
            "things I am learning, places I discover and "
            "moments that do not always make it onto "
            "social media."
        ),
        profile_image_url=None,
        intro_reel_url=None,
        instagram_url=None,
        tiktok_url=None,
        youtube_url=None,
    )

    db.session.add(
        creator
    )

    # ========================================================
    # CATEGORIES / FOLDERS
    # ========================================================

    click.echo(
        "Creating content folders..."
    )

    lifestyle = ContentCategory(
        creator_account_id=creator_account.id,
        name="Lifestyle",
        slug="lifestyle",
        description=(
            "Daily life, routines and the little things."
        ),
        display_order=1,
    )

    personal = ContentCategory(
        creator_account_id=creator_account.id,
        name="Personal",
        slug="personal",
        description=(
            "Personal stories, thoughts and conversations."
        ),
        display_order=2,
    )

    travel = ContentCategory(
        creator_account_id=creator_account.id,
        name="Travel",
        slug="travel",
        description=(
            "Places, trips and experiences."
        ),
        display_order=3,
    )

    behind_scenes = ContentCategory(
        creator_account_id=creator_account.id,
        name="Behind the Scenes",
        slug="behind-the-scenes",
        description=(
            "A closer look at life behind the content."
        ),
        display_order=4,
    )

    conversations = ContentCategory(
        creator_account_id=creator_account.id,
        name="Conversations",
        slug="conversations",
        description=(
            "Things worth talking about."
        ),
        display_order=5,
    )

    db.session.add_all(
        [
            lifestyle,
            personal,
            travel,
            behind_scenes,
            conversations,
        ]
    )

    db.session.flush()

    # ========================================================
    # STORY 1
    # ========================================================

    click.echo(
        "Creating sample stories..."
    )

    create_post(
        creator_account=creator_account,
        title="Learning to Enjoy the Quiet Seasons",
        slug="learning-to-enjoy-the-quiet-seasons",
        excerpt=(
            "Not every season of life needs to be "
            "loud, busy or visible."
        ),
        body="""
There are moments when life becomes quieter than we expected.

At first, that quiet can feel uncomfortable.

We become so used to constantly moving, achieving, posting,
planning and trying to figure out what comes next that silence
can almost feel like something is wrong.

But lately I have been learning that quiet seasons have their
own purpose.

Sometimes slowing down gives us the space to hear ourselves
again.

It gives us time to notice what we actually enjoy, what we have
outgrown and what deserves more of our attention.

Maybe every chapter does not need to look impressive from the
outside.

Some chapters are simply preparing us for what comes next.
""".strip(),
        content_type="story",
        category=personal,
        access_level="public",
        is_featured=True,
        days_ago=0,
    )

    # ========================================================
    # STORY 2
    # ========================================================

    create_post(
        creator_account=creator_account,
        title="Five Things Making Me Happy Right Now",
        slug="five-things-making-me-happy-right-now",
        excerpt=(
            "A small collection of things bringing "
            "a little more joy into my days."
        ),
        body="""
I wanted to share something simple today.

Here are five things making me happy lately:

Slow mornings.

Good conversations.

Finding new places to eat.

Taking photos without worrying about posting them.

And spending more time with people who make life feel lighter.

Sometimes happiness really is hidden inside ordinary moments.
""".strip(),
        content_type="story",
        category=lifestyle,
        access_level="public",
        days_ago=2,
    )

    # ========================================================
    # STORY 3
    # ========================================================

    create_post(
        creator_account=creator_account,
        title="The Weekend I Needed",
        slug="the-weekend-i-needed",
        excerpt=(
            "Sometimes getting away for a little while "
            "is enough to reset everything."
        ),
        body="""
This weekend reminded me why changing your environment can be
so refreshing.

Nothing dramatic happened.

There was good food, long conversations, a few beautiful views
and enough time to stop checking the clock.

I came home feeling lighter.

I think we sometimes underestimate how important it is to give
ourselves space away from our normal routines.
""".strip(),
        content_type="story",
        category=travel,
        access_level="public",
        days_ago=5,
    )

    # ========================================================
    # PUBLIC REEL
    # ========================================================

    click.echo(
        "Creating sample reels..."
    )

    reel = create_post(
        creator_account=creator_account,
        title="A Little Sunday Reset",
        slug="a-little-sunday-reset",
        excerpt=(
            "Cleaning, coffee, planning and getting "
            "ready for another week."
        ),
        body=(
            "A few moments from my Sunday "
            "reset routine."
        ),
        content_type="reel",
        category=lifestyle,
        access_level="public",
        days_ago=1,
    )

    # ========================================================
    # PUBLIC VLOG
    # ========================================================

    click.echo(
        "Creating sample vlogs..."
    )

    vlog = create_post(
        creator_account=creator_account,
        title="Spend the Day With Me",
        slug="spend-the-day-with-me",
        excerpt=(
            "Come with me through an ordinary day "
            "of work, food, errands and creating."
        ),
        body=(
            "An everyday vlog showing a little more "
            "of what my days actually look like."
        ),
        content_type="vlog",
        category=behind_scenes,
        access_level="public",
        days_ago=3,
    )

    # ========================================================
    # EXCLUSIVE VLOG 1
    # ========================================================

    click.echo(
        "Creating exclusive content..."
    )

    exclusive_one = create_post(
        creator_account=creator_account,
        title="Life Update: Let's Talk",
        slug="exclusive-life-update-lets-talk",
        excerpt=(
            "A more personal conversation about what "
            "has been happening behind the scenes."
        ),
        body=(
            "This vlog is available exclusively "
            "to active members."
        ),
        content_type="vlog",
        category=personal,
        access_level="subscriber",
        is_featured=True,
        days_ago=4,
    )

    # ========================================================
    # EXCLUSIVE VLOG 2
    # ========================================================

    exclusive_two = create_post(
        creator_account=creator_account,
        title="Behind the Content",
        slug="behind-the-content",
        excerpt=(
            "What creating content actually looks like "
            "before anything gets posted."
        ),
        body=(
            "An exclusive behind-the-scenes vlog "
            "for members."
        ),
        content_type="vlog",
        category=behind_scenes,
        access_level="subscriber",
        days_ago=7,
    )

    # ========================================================
    # EXCLUSIVE STORY
    # ========================================================

    create_post(
        creator_account=creator_account,
        title="What I Don't Usually Share Online",
        slug="what-i-dont-usually-share-online",
        excerpt=(
            "A more personal story for the people "
            "supporting this space."
        ),
        body="""
Some things are difficult to fit into a thirty-second video.

This space gives me somewhere to have longer and more honest
conversations.

Thank you for supporting what I create and allowing this
community to exist.
""".strip(),
        content_type="story",
        category=conversations,
        access_level="subscriber",
        days_ago=9,
    )

    # ========================================================
    # DEVELOPMENT MEDIA PLACEHOLDERS
    # ========================================================

    _ = (
        reel,
        vlog,
        exclusive_one,
        exclusive_two,
    )

    # ========================================================
    # SAMPLE EMAIL SUBSCRIBER
    # ========================================================

    click.echo(
        "Creating development email subscriber..."
    )

    email_subscriber = EmailSubscriber(
        creator_account_id=creator_account.id,
        email="demo@example.com",
        status="active",
        verification_token=None,
        unsubscribe_token=(
            "development-unsubscribe-token"
        ),
        verified_at=utc_now(),
    )

    db.session.add(
        email_subscriber
    )

    # ========================================================
    # COMMIT
    # ========================================================

    db.session.commit()

    # ========================================================
    # SUMMARY
    # ========================================================

    post_count = (
        ContentPost.query
        .filter_by(
            creator_account_id=creator_account.id
        )
        .count()
    )

    category_count = (
        ContentCategory.query
        .filter_by(
            creator_account_id=creator_account.id
        )
        .count()
    )

    subscriber_count = (
        EmailSubscriber.query
        .filter_by(
            creator_account_id=creator_account.id
        )
        .count()
    )

    public_count = (
        ContentPost.query
        .filter_by(
            creator_account_id=creator_account.id,
            access_level="public",
        )
        .count()
    )

    exclusive_count = (
        ContentPost.query
        .filter_by(
            creator_account_id=creator_account.id,
            access_level="subscriber",
        )
        .count()
    )

    click.echo("")
    click.echo(
        "========================================"
    )
    click.echo(
        " Seed completed successfully"
    )
    click.echo(
        "========================================"
    )
    click.echo("")

    click.echo(
        f"Creator: {creator.display_name}"
    )

    click.echo(
        f"Creator account: @{creator_account.username}"
    )

    click.echo(
        f"Folders: {category_count}"
    )

    click.echo(
        f"Posts: {post_count}"
    )

    click.echo(
        f"Public content: {public_count}"
    )

    click.echo(
        f"Exclusive content: {exclusive_count}"
    )

    click.echo(
        f"Email subscribers: {subscriber_count}"
    )

    click.echo("")

    click.echo(
        "Open: http://127.0.0.1:5000"
    )

    click.echo("")
