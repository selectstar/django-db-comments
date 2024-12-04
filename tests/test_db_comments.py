#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_django-db-comments
------------

Tests for `django-db-comments` module.
"""

from mock import patch
from psycopg2 import sql

from django.apps import apps
from django.db import models, DEFAULT_DB_ALIAS
from django.test import TestCase, TransactionTestCase

try:
    from django.utils.translation import ugettext_lazy as _
except ImportError:
    # django 4.0 removed ugettext_lazy
    from django.utils.translation import gettext_lazy as _

from django_db_comments.db_comments import (
    get_comments_for_model,
    add_column_comments_to_database,
    add_table_comments_to_database,
    POSTGRES_COMMENT_SQL,
    POSTGRES_COMMENT_ON_TABLE_SQL,
    copy_help_texts_to_database,
)


class TestDjangoDbComments(TestCase):
    def test_get_comments_for_model(self):
        class Model(models.Model):
            no_comment = models.TextField()
            verbose_name = models.TextField("This is verbose name")
            help_text = models.TextField(
                help_text="I am really should see this in database"
            )

            class Meta:
                app_label = "unit_test"

        column_comments = get_comments_for_model(Model)
        self.assertDictEqual(
            column_comments,
            {
                "verbose_name": "This is verbose name",
                "help_text": "I am really should see this in database",
            },
        )

    def get_comments_for_model_with_inherited_fields(self):
        class BaseModel(models.Model):
            first_name = models.CharField(max_length=50)
            last_name = models.CharField(max_length=50)
            date_of_birth = models.DateField()

            class Meta:
                app_label = "unit_test"

        class InheritingModel(BaseModel):
            no_comment = models.TextField()
            verbose_name = models.TextField("This is a verbose name")
            help_text = models.TextField(
                help_text="I really should see this in the database"
            )

            class Meta:
                app_label = "unit_test"

        column_comments = get_comments_for_model(InheritingModel)
        self.assertDictEqual(
            column_comments,
            {
                "verbose_name": "This is a verbose name",
                "help_text": "I really should see this in the database",
            },
        )

    @patch("django_db_comments.db_comments.connections")
    def test_add_column_comments_to_database(self, mock_connections):
        mock_cursor = mock_connections.__getitem__(
            DEFAULT_DB_ALIAS
        ).cursor.return_value.__enter__.return_value

        model_table = "model"
        table_column = "verbose_name"
        comment = "This is verbose name"

        add_column_comments_to_database({model_table: {table_column: comment}})

        query = POSTGRES_COMMENT_SQL.format(
            sql.Identifier(model_table), sql.Identifier(table_column)
        )

        # Demonstrating assert_* options:
        mock_cursor.execute.assert_called_once()
        mock_cursor.execute.assert_called()
        mock_cursor.execute.assert_called_once_with(query, [comment])

    @patch("django_db_comments.db_comments.connections")
    def test_add_table_comments_to_database(self, mock_connections):
        mock_cursor = mock_connections.__getitem__(
            DEFAULT_DB_ALIAS
        ).cursor.return_value.__enter__.return_value

        model_table = "model"
        comment = "This is verbose name"

        add_table_comments_to_database({model_table: comment})

        query = POSTGRES_COMMENT_ON_TABLE_SQL.format(
            sql.Identifier(model_table), sql.Identifier(comment)
        )

        # Demonstrating assert_* options:
        mock_cursor.execute.assert_called_once()
        mock_cursor.execute.assert_called()
        mock_cursor.execute.assert_called_once_with(query, [comment])

    def test_ugettext_lazy_workaround(self):
        class GettextLazyModel(models.Model):
            # Example from Django auth.User
            is_superuser = models.BooleanField(
                _("superuser status"),
                help_text=_(
                    "Designates that this user has all permissions without "
                    "explicitly assigning them."
                ),
            )

            class Meta:
                app_label = "unit_test"

        column_comments = get_comments_for_model(GettextLazyModel)
        self.assertDictEqual(
            column_comments,
            {
                "is_superuser": "superuser status | Designates that this user has all "
                "permissions without explicitly assigning them."
            },
        )

class TestDbcommentsSignal(TransactionTestCase):
    available_apps = ["django_db_comments", "tests"]
    def test_post_migrate_signal(self):
        app_config = apps.get_app_config("tests")
        with patch(
            "django_db_comments.db_comments._check_app_config", return_value=True
        ):
            with patch(
                "django_db_comments.db_comments.add_column_comments_to_database",
                return_value=True,
            ) as mock_column_comments:
                with patch(
                    "django_db_comments.db_comments.add_table_comments_to_database",
                    return_value=True,
                ) as mock_table_comments:
                    with patch("django_db_comments.db_comments.PROCESSED_APPS", set()):
                        copy_help_texts_to_database(app_config)
                        mock_table_comments.assert_called_once_with(
                            {"tests_examplemodel": "This Is An Example For Table Comment"},
                            "default",
                        )
                        mock_column_comments.assert_called_once_with(
                            {"tests_examplemodel": {"created_at": "model creation time"}},
                            "default",
                        )
                        # make sure they're not called multiple times
                        mock_table_comments.reset_mock()
                        mock_column_comments.reset_mock()

                        copy_help_texts_to_database(app_config)
                        mock_table_comments.assert_not_called()
                        mock_column_comments.assert_not_called()
