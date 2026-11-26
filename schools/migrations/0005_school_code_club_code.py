# 学校ID（School.code）と部活動ID（Club.code）を追加する。
# すでにある学校は、これまでの学校アカウントのID（username）をそのまま学校IDにする。
# すでにある部活動の部活動IDは「club＋番号」にする（教育委員会があとで伝える）。

import re

from django.db import migrations, models

import schools.models


def fill_codes(apps, schema_editor):
    School = apps.get_model("schools", "School")
    Club = apps.get_model("schools", "Club")
    User = apps.get_model("accounts", "User")

    used = set()
    for school in School.objects.order_by("pk"):
        account = (User.objects.filter(school=school, role="teacher")
                   .order_by("pk").first())
        code = account.username if account else ""
        if not code or code in used or not code.replace("-", "").replace("_", "").isascii() \
                or not code.replace("-", "").replace("_", "").isalnum():
            code = f"school{school.pk}"
        used.add(code)
        school.code = code
        school.save(update_fields=["code"])

    for club in Club.objects.all():
        club.code = f"club{club.pk}"
        club.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("schools", "0004_club_desired_level_tournamentresult"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="code",
            field=models.CharField(max_length=30, null=True, verbose_name="学校ID"),
        ),
        migrations.AddField(
            model_name="club",
            name="code",
            field=models.CharField(max_length=30, null=True, verbose_name="部活動ID"),
        ),
        migrations.RunPython(fill_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="school",
            name="code",
            field=models.CharField(
                help_text="ログイン時に入力するIDです。半角英数字で入力してください。",
                max_length=30, unique=True,
                validators=[schools.models.login_code_validator], verbose_name="学校ID"),
        ),
        migrations.AlterField(
            model_name="club",
            name="code",
            field=models.CharField(
                help_text="ログイン時に、学校IDと一緒に入力するIDです。同じ学校の中で重ならないようにしてください。",
                max_length=30,
                validators=[schools.models.login_code_validator], verbose_name="部活動ID"),
        ),
        migrations.AddConstraint(
            model_name="club",
            constraint=models.UniqueConstraint(fields=("school", "code"), name="unique_club_code_in_school"),
        ),
    ]
