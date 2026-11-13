from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from schools.models import Area, Club, School, Sport
from .models import Availability, MatchResult, Message, PracticeMatch


class MatchingFeatureTestBase(TestCase):
    """A高校・B高校・C高校の3校と、A高校とB高校のあいだの試合を用意する"""

    @classmethod
    def setUpTestData(cls):
        area = Area.objects.create(name="札幌地区")
        sport = Sport.objects.create(name="サッカー")
        cls.school_a = School.objects.create(name="A高校", area=area, address="札幌市", latitude=43.0, longitude=141.0)
        cls.school_b = School.objects.create(name="B高校", area=area, address="札幌市", latitude=43.1, longitude=141.1)
        cls.school_c = School.objects.create(name="C高校", area=area, address="札幌市", latitude=43.2, longitude=141.2)
        cls.user_a = User.objects.create_user(username="a", password="x", role="teacher", school=cls.school_a)
        cls.user_b = User.objects.create_user(username="b", password="x", role="teacher", school=cls.school_b)
        cls.user_c = User.objects.create_user(username="c", password="x", role="teacher", school=cls.school_c)
        cls.club_a = Club.objects.create(school=cls.school_a, sport=sport, gender="male")
        cls.club_b = Club.objects.create(school=cls.school_b, sport=sport, gender="male")
        Club.objects.create(school=cls.school_c, sport=sport, gender="male")

        today = timezone.localdate()
        cls.past_match = PracticeMatch.objects.create(
            applicant_club=cls.club_a, opponent_club=cls.club_b, date=today - timedelta(days=3),
            venue_kind="applicant", status=PracticeMatch.Status.CONFIRMED)
        cls.future_match = PracticeMatch.objects.create(
            applicant_club=cls.club_b, opponent_club=cls.club_a, date=today + timedelta(days=5),
            venue_kind="opponent", status=PracticeMatch.Status.CONFIRMED)

        cls.common_day = today + timedelta(days=10)
        Availability.objects.create(club=cls.club_a, date=cls.common_day, can_host=True)
        Availability.objects.create(club=cls.club_b, date=cls.common_day)


class PlannedAndResultTest(MatchingFeatureTestBase):

    def test_planned_list_splits_upcoming_and_past(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("planned_matches"))
        self.assertEqual([r["match"] for r in response.context["upcoming"]], [self.future_match])
        self.assertEqual([r["match"] for r in response.context["past"]], [self.past_match])

    def test_cannot_record_result_before_match_day(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("match_result_edit", args=[self.future_match.pk]))
        self.assertRedirects(response, reverse("planned_matches"))

    def test_record_result_and_view_from_both_schools(self):
        self.client.force_login(self.user_b)   # 相手側（B高校）が登録する
        response = self.client.post(
            reverse("match_result_edit", args=[self.past_match.pk]),
            {"applicant_score": 3, "opponent_score": 1, "notes": "よい試合でした"},
        )
        self.assertRedirects(response, reverse("match_results"))
        result = MatchResult.objects.get(match=self.past_match)
        self.assertEqual(result.updated_by, self.school_b)

        # B高校から見ると 1-3 で負け
        response = self.client.get(reverse("match_results"))
        row = response.context["results"][0]
        self.assertEqual((row["my_score"], row["their_score"], row["outcome"]), (1, 3, "lose"))

        # A高校から見ると 3-1 で勝ち。編集もできる
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("match_results"))
        self.assertEqual(response.context["record"], {"win": 1, "lose": 0, "draw": 0})
        response = self.client.get(reverse("match_result_edit", args=[self.past_match.pk]))
        self.assertEqual(response.status_code, 200)

    def test_negative_score_is_rejected(self):
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse("match_result_edit", args=[self.past_match.pk]),
            {"applicant_score": -1, "opponent_score": 0},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MatchResult.objects.exists())

    def test_other_school_cannot_touch_result(self):
        result = MatchResult.objects.create(match=self.past_match, applicant_score=1, opponent_score=0)
        self.client.force_login(self.user_c)
        self.assertEqual(
            self.client.get(reverse("match_result_edit", args=[self.past_match.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("match_result_delete", args=[result.pk])).status_code, 404)

    def test_delete_result(self):
        result = MatchResult.objects.create(match=self.past_match, applicant_score=1, opponent_score=0)
        self.client.force_login(self.user_a)
        self.client.post(reverse("match_result_delete", args=[result.pk]))
        self.assertFalse(MatchResult.objects.exists())
        self.assertTrue(PracticeMatch.objects.filter(pk=self.past_match.pk).exists())


class MessageTest(MatchingFeatureTestBase):

    def test_send_and_read_message(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("message_room", args=[self.school_b.pk]), {"content": "こんにちは"})
        self.assertEqual(response.status_code, 302)
        message = Message.objects.get()
        self.assertEqual((message.sender, message.receiver, message.is_read), (self.school_a, self.school_b, False))

        # B高校のサイドバーに未読件数が出て、会話を開くと既読になる
        self.client.force_login(self.user_b)
        response = self.client.get(reverse("teacher_home"))
        self.assertContains(response, 'class="sidebar-badge"')
        response = self.client.get(reverse("message_list"))
        self.assertEqual(response.context["conversations"][0]["unread"], 1)
        self.client.get(reverse("message_room", args=[self.school_a.pk]))
        message.refresh_from_db()
        self.assertTrue(message.is_read)

    def test_blank_message_is_rejected(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("message_room", args=[self.school_b.pk]), {"content": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Message.objects.exists())

    def test_cannot_message_own_school(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("message_room", args=[self.school_a.pk]))
        self.assertEqual(response.status_code, 404)

    def test_partner_school_listed_first(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("message_list"))
        self.assertEqual(response.context["available_schools"][0], self.school_b)


class ScheduleTest(MatchingFeatureTestBase):

    def test_common_dates_and_request_link(self):
        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse("schedule") + f"?club={self.club_a.pk}&opponent={self.club_b.pk}")
        candidates = response.context["candidates"]
        self.assertEqual([c["date"] for c in candidates], [self.common_day])
        self.assertTrue(candidates[0]["my_host"])
        link = reverse("match_request", args=[self.club_a.pk, self.club_b.pk])
        self.assertContains(response, f"{link}?date={self.common_day:%Y-%m-%d}")

        # リンク先の申し込み画面では、日付が入っている
        response = self.client.get(f"{link}?date={self.common_day:%Y-%m-%d}")
        self.assertEqual(str(response.context["form"]["date"].value()), f"{self.common_day:%Y-%m-%d}")

    def test_already_requested_date_is_marked(self):
        PracticeMatch.objects.create(
            applicant_club=self.club_b, opponent_club=self.club_a, date=self.common_day, venue_kind="applicant")
        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse("schedule") + f"?club={self.club_a.pk}&opponent={self.club_b.pk}")
        self.assertEqual(response.context["candidates"][0]["requested"], "申込中")

    def test_other_schools_club_cannot_be_selected(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("schedule") + f"?club={self.club_b.pk}")
        self.assertIsNone(response.context["selected_club"])
