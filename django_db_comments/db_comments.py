from psycopg2 import sql

from django.apps import apps as global_apps
from django.db import DEFAULT_DB_ALIAS, router, connections, transaction
from django.conf import settings

# django engines support
# 'django.db.backends.postgresql'
# 'django.db.backends.postgresql_psycopg2'
# 'django.db.backends.mysql'
# 'django.db.backends.sqlite3'
# 'django.db.backends.oracle'
ALLOWED_ENGINES = [
    "django.db.backends.postgresql",
    "django.contrib.gis.db.backends.postgis",
    "django.db.backends.postgresql_psycopg2",
    "psqlextra.backend",
]

# http://initd.org/psycopg/docs/sql.html
# https://www.postgresql.org/docs/9.6/sql-comment.html
POSTGRES_COMMENT_SQL = sql.SQL("COMMENT ON COLUMN {}.{} IS %s")

POSTGRES_COMMENT_ON_TABLE_SQL = sql.SQL("COMMENT ON TABLE {} IS %s")

# For TransactionTestCase tests, the post_migrate signal is fired as part of a flush
# operation after each test. We keep track of the apps we've synced the comments for
# in order to avoid syncing db comments after each test.
PROCESSED_APPS = set()


def get_comments_for_model(model):
    column_comments = {}

    for field in model._meta.fields:
        # if the field is not inherited - continue
        if field.model == model:
            comment = []
            # Check if verbose name was not autogenerated, according to django code
            # https://github.com/django/django/blob/9681e96/django/db/models/fields/__init__.py#L724
            if field.verbose_name.lower() != field.name.lower().replace("_", " "):
                comment.append(
                    str(field.verbose_name)
                )  # str() is workaround for Django.ugettext_lazy
            if field.help_text:
                comment.append(
                    str(field.help_text)
                )  # str() is workaround for Django.ugettext_lazy
            if comment:
                column_comments[field.column] = " | ".join(comment)

    return column_comments


def add_column_comments_to_database(columns_comments, using=DEFAULT_DB_ALIAS):
    with connections[using].cursor() as cursor:
        with transaction.atomic():
            for table, columns in columns_comments.items():

                for column, comment in columns.items():
                    query = POSTGRES_COMMENT_SQL.format(
                        sql.Identifier(table), sql.Identifier(column)
                    )
                    cursor.execute(query, [comment])


def add_table_comments_to_database(table_comment_dict, using=DEFAULT_DB_ALIAS):
    with connections[using].cursor() as cursor:
        with transaction.atomic():
            for table, comment in table_comment_dict.items():
                query_for_table_comment = POSTGRES_COMMENT_ON_TABLE_SQL.format(
                    sql.Identifier(table)
                )
                cursor.execute(query_for_table_comment, [comment])


def _check_app_config(app_config, using):
    app_label = app_config.label
    if not app_config.models_module:
        return False

    if settings.DATABASES[using]["ENGINE"] not in ALLOWED_ENGINES:
        return False

    if not router.allow_migrate(using, app_label):
        return False
    return True


def copy_help_texts_to_database(
    app_config,
    verbosity=2,
    interactive=True,
    using=DEFAULT_DB_ALIAS,
    apps=global_apps,
    **kwargs
):
    """
    Create content types for models in the given app.
    """
    if app_config in PROCESSED_APPS:
        return
    PROCESSED_APPS.add(app_config)
    if not _check_app_config(app_config, using):
        return

    app_models = [
        app_model
        for app_model in apps.get_models()
        if not any(
            [
                app_model._meta.abstract,
                app_model._meta.proxy,
                not app_model._meta.managed,
            ]
        )
    ]

    columns_comments = {
        model._meta.db_table: get_comments_for_model(model) for model in app_models
    }

    if columns_comments:
        add_column_comments_to_database(columns_comments, using)

    table_comments = {
        model._meta.db_table: model._meta.verbose_name.title()
        for model in app_models
        if model._meta.verbose_name
    }

    if table_comments:
        add_table_comments_to_database(table_comments, using)

    if verbosity >= 2:
        for table, columns in columns_comments.items():
            for column, comment in columns.items():
                print("Adding comment in %s for %s = '%s'" % (table, column, comment))

        for table, comment in table_comments.items():
            print("Adding comment to %s = '%s'" % (table, comment))
