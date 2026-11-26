# アカウントを「学校ごと」から「部活動ごと」に変える。
# すでにある部活動それぞれにアカウントを作り、その学校の今までのアカウントの
# パスワードと利用状態を引き継ぐ（今までと同じパスワードでログインできる）。
# 学校ごとのアカウントは使わなくなるので削除する。

import django.db.models.deletion
from django.contrib.auth.hashers import make_password
from django.db import migrations, models


def create_club_accounts(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Club = apps.get_model("schools", "Club")

    old_accounts = User.objects.filter(role="teacher", club__isnull=True)
    by_school = {}
    for account in old_accounts.order_by("pk"):
        if account.school_id is not None:
            by_school.setdefault(account.school_id, account)

    for club in Club.objects.filter(account__isnull=True):
        old = by_school.get(club.school_id)
        username = f"club{club.pk}"
        while User.objects.filter(username=username).exists():
            username += "_"
        User.objects.create(
            username=username,
            password=old.password if old else make_password(None),
            is_active=old.is_active if old else True,
            role="teacher",
            school_id=club.school_id,
            club=club,
        )

    old_accounts.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("schools", "0005_school_code_club_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="club",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="account", to="schools.club", verbose_name="部活動"),
        ),
        migrations.RunPython(create_club_accounts, migrations.RunPython.noop),
    ]
