# 学校情報（School）を学校アカウント（role=school の User）にひも付ける。
# これまでの学校ID（School.code）は、学校アカウントのID（username）に移す。
# 学校アカウントのパスワードは未設定にする（教育委員会が「学校アカウント管理」の編集で設定する）。
# あわせて、学校情報に連絡先と対応競技を追加する。

import django.db.models.deletion
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations, models

import schools.models


def create_school_accounts(apps, schema_editor):
    School = apps.get_model("schools", "School")
    User = apps.get_model("accounts", "User")
    for school in School.objects.order_by("pk"):
        username = school.code or f"school{school.pk}"
        while User.objects.filter(username=username).exists():
            username += "_"
        school.account = User.objects.create(
            username=username, password=make_password(None), role="school")
        school.save(update_fields=["account"])


def restore_codes(apps, schema_editor):
    School = apps.get_model("schools", "School")
    for school in School.objects.select_related("account"):
        school.code = school.account.username
        school.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_roles_advisor"),
        ("schools", "0006_remove_area"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="account",
            field=models.OneToOneField(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="school_profile", to=settings.AUTH_USER_MODEL, verbose_name="学校アカウント"),
        ),
        migrations.RunPython(create_school_accounts, restore_codes),
        migrations.AlterField(
            model_name="school",
            name="account",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="school_profile", to=settings.AUTH_USER_MODEL, verbose_name="学校アカウント"),
        ),
        migrations.RemoveField(model_name="school", name="code"),
        migrations.AddField(
            model_name="school",
            name="phone",
            field=models.CharField(blank=True, max_length=30, verbose_name="連絡先"),
        ),
        migrations.AddField(
            model_name="school",
            name="sports",
            field=models.ManyToManyField(blank=True, related_name="schools", to="schools.sport", verbose_name="対応競技"),
        ),
        migrations.AlterField(
            model_name="club",
            name="code",
            field=models.CharField(
                help_text="部活動アカウントの登録とログインで、学校IDと一緒に入力するIDです。同じ学校の中で重ならないようにしてください。",
                max_length=30, validators=[schools.models.login_code_validator], verbose_name="部活ID"),
        ),
    ]
