from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0002_area_school_area'),
    ]

    operations = [
        migrations.AddField(
            model_name='sport',
            name='icon',
            field=models.CharField(blank=True, help_text='競技に合った絵文字を入力してください。（例：⚽）', max_length=20, verbose_name='競技アイコン'),
        ),
    ]
