"""
デザインの更新（2026-11-17）に合わせた仕組みの変更。

1. 申し込み：候補日（CandidateDate）を複数持てるようにする。
   PracticeMatch.date は「確定した試合日」になり、確定するまでは空。
2. 試合結果：両校がそれぞれ自校の得点・備考を入力する形にする。
3. メッセージ：会話（Conversation）を作り、メッセージは会話に属する形にする。

すでにあるデータは、次のように移し替える。
  ・申し込みの日付 → 候補日。確定していない申し込みは、確定日を空にする
  ・試合結果の備考 → 最後に登録した学校の側の備考
  ・メッセージ → 学校の組み合わせごとの「以前の会話」
"""
import django.db.models.deletion
from django.db import migrations, models


def forwards(apps, schema_editor):
    PracticeMatch = apps.get_model("matching", "PracticeMatch")
    CandidateDate = apps.get_model("matching", "CandidateDate")
    MatchResult = apps.get_model("matching", "MatchResult")
    Conversation = apps.get_model("matching", "Conversation")
    Message = apps.get_model("matching", "Message")

    # 1. 申し込みの日付を候補日へ
    for match in PracticeMatch.objects.all():
        if match.date:
            CandidateDate.objects.get_or_create(match=match, date=match.date)
        if match.status != "confirmed":
            match.date = None
            match.save(update_fields=["date"])

    # 2. 試合結果の備考を、登録した学校の側へ
    for result in MatchResult.objects.select_related("match__applicant_club"):
        if not result.notes:
            continue
        if result.updated_by_id and result.updated_by_id != result.match.applicant_club.school_id:
            result.opponent_notes = result.notes
        else:
            result.applicant_notes = result.notes
        result.save(update_fields=["applicant_notes", "opponent_notes"])

    # 3. メッセージを、学校の組み合わせごとの「以前の会話」へ
    conversations = {}
    for message in Message.objects.order_by("created_at"):
        key = frozenset([message.sender_id, message.receiver_id])
        conversation = conversations.get(key)
        if conversation is None:
            conversation = Conversation.objects.create(
                school_a_id=message.sender_id, school_b_id=message.receiver_id,
            )
            conversations[key] = conversation
        message.conversation = conversation
        message.save(update_fields=["conversation"])
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=["last_message_at"])


class Migration(migrations.Migration):

    dependencies = [
        ('matching', '0003_matchresult_message'),
        ('schools', '0003_sport_icon'),
    ]

    operations = [
        # ---------- 申し込み ----------
        migrations.CreateModel(
            name='CandidateDate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='候補日')),
                ('match', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='candidates', to='matching.practicematch', verbose_name='申し込み')),
            ],
            options={
                'ordering': ['date'],
                'unique_together': {('match', 'date')},
            },
        ),
        migrations.AlterField(
            model_name='practicematch',
            name='date',
            field=models.DateField(blank=True, null=True, verbose_name='確定した試合日'),
        ),
        migrations.AlterField(
            model_name='practicematch',
            name='message',
            field=models.TextField(blank=True, verbose_name='備考・連絡事項'),
        ),
        migrations.AlterField(
            model_name='practicematch',
            name='status',
            field=models.CharField(choices=[('pending', '申込中'), ('confirmed', '確定'), ('declined', 'お断り')], default='pending', max_length=10, verbose_name='状態'),
        ),
        migrations.AlterField(
            model_name='practicematch',
            name='decided_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='確定・お断りの日時'),
        ),
        migrations.AlterModelOptions(
            name='practicematch',
            options={'ordering': ['-created_at']},
        ),

        # ---------- 試合結果 ----------
        migrations.AlterField(
            model_name='matchresult',
            name='applicant_score',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='申込側の得点'),
        ),
        migrations.AlterField(
            model_name='matchresult',
            name='opponent_score',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='相手側の得点'),
        ),
        migrations.AddField(
            model_name='matchresult',
            name='applicant_notes',
            field=models.TextField(blank=True, verbose_name='申込側の試合内容・備考'),
        ),
        migrations.AddField(
            model_name='matchresult',
            name='opponent_notes',
            field=models.TextField(blank=True, verbose_name='相手側の試合内容・備考'),
        ),

        # ---------- 会話 ----------
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='作成日時')),
                ('last_message_at', models.DateTimeField(blank=True, null=True, verbose_name='最後のメッセージの日時')),
                ('club_a', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='schools.club', verbose_name='部活動（開始した側）')),
                ('club_b', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='schools.club', verbose_name='部活動（相手側）')),
                ('match', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conversation', to='matching.practicematch', verbose_name='申し込み')),
                ('school_a', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='schools.school', verbose_name='学校（開始した側）')),
                ('school_b', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='schools.school', verbose_name='学校（相手側）')),
            ],
            options={
                'ordering': ['-last_message_at', '-created_at'],
            },
        ),
        migrations.AddField(
            model_name='message',
            name='conversation',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='matching.conversation', verbose_name='会話'),
        ),

        # ---------- 今あるデータの移し替え ----------
        migrations.RunPython(forwards, migrations.RunPython.noop),

        # ---------- 使わなくなった項目の削除 ----------
        migrations.RemoveField(model_name='matchresult', name='notes'),
        migrations.RemoveField(model_name='matchresult', name='updated_by'),
        migrations.RemoveField(model_name='message', name='receiver'),
        migrations.AlterField(
            model_name='message',
            name='conversation',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='matching.conversation', verbose_name='会話'),
        ),
    ]
