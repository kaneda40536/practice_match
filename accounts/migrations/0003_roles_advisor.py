# 役割に「学校（学校アカウント）」と「部活動」を追加し、顧問名を持てるようにする。
# これまで「顧問（teacher）」としていた部活動のアカウントは「部活動（club）」に移す。

import django.db.models.deletion
from django.db import migrations, models


def club_accounts_to_club_role(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(club__isnull=False).update(role="club")
    # createsuperuser で作ったアカウントは、教育委員会（管理者）にする
    User.objects.filter(is_superuser=True, club__isnull=True).update(role="board")


def club_role_to_teacher(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="club").update(role="teacher")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_club"),
        ("schools", "0006_remove_area"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[("board", "教育委員会"), ("school", "学校"), ("teacher", "顧問"), ("club", "部活動")],
                default="club", max_length=10, verbose_name="役割"),
        ),
        migrations.AddField(
            model_name="user",
            name="advisor_name",
            field=models.CharField(blank=True, max_length=100, verbose_name="顧問名"),
        ),
        migrations.AlterField(
            model_name="user",
            name="school",
            field=models.ForeignKey(
                blank=True, help_text="顧問・部活動のアカウントの学校", null=True,
                on_delete=django.db.models.deletion.CASCADE, to="schools.school", verbose_name="所属学校"),
        ),
        migrations.RunPython(club_accounts_to_club_role, club_role_to_teacher),
    ]
