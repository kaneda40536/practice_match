from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from schools.models import Area, Club, School, Sport
from .models import Availability, CandidateDate, Conversation, MatchResult, Message, PracticeMatch


class MatchingFeatureTestBase(TestCase):
    """A高校・B高校・C高校の3校と、A高校とB高校のあいだの確定済みの試合を用意する"""

    @classmethod
    def setUpTestData(cls):
        area = Area.objects.create(name="札幌地区")
        cls.sport = Sport.objects.create(name="サッカー", icon="⚽")
        cls.school_a = School.objects.create(name="A高校", area=area, address="札幌市", latitude=43.0, longitude=141.0)
        cls.school_b = School.objects.create(name="B高校", area=area, address="札幌市", latitude=43.1, longitude=141.1)
        cls.school_c = School.objects.create(name="C高校", area=area, address="札幌市", latitude=43.2, longitude=141.2)
        cls.user_a = User.objects.create_user(username="a", password="x", role="teacher", school=cls.school_a)
        cls.user_b = User.objects.create_user(username="b", password="x", role="teacher", school=cls.school_b)
        cls.user_c = User.objects.create_user(username="c", password="x", role="teacher", school=cls.school_c)
        cls.club_a = Club.objects.create(school=cls.school_a, sport=cls.sport, gender="male")
        cls.club_b = Club.objects.create(school=cls.school_b, sport=cls.sport, gender="male")
        cls.club_c = Club.objects.create(school=cls.school_c, sport=cls.sport, gender="male")

        cls.today = timezone.localdate()
        cls.past_match = PracticeMatch.objects.create(
            applicant_club=cls.club_a, opponent_club=cls.club_b, date=cls.today - timedelta(days=3),
            venue_kind="applicant", status=PracticeMatch.Status.CONFIRMED)
        cls.future_match = PracticeMatch.objects.create(
            applicant_club=cls.club_b, opponent_club=cls.club_a, date=cls.today + timedelta(days=5),
            venue_kind="opponent", status=PracticeMatch.Status.CONFIRMED)

        cls.day1 = cls.today + timedelta(days=10)
        cls.day2 = cls.today + timedelta(days=11)
        Availability.objects.create(club=cls.club_a, date=cls.day1, can_host=True)
        Availability.objects.create(club=cls.club_b, date=cls.day1)
        Availability.objects.create(club=cls.club_a, date=cls.day2)
        Availability.objects.create(club=cls.club_b, date=cls.day2)


class ProposalTest(MatchingFeatureTestBase):
    """候補日付き申し込み：申込側が候補日を複数送り、相手側が1日を選んで確定する"""

    def request_url(self):
        return reverse("match_request", args=[self.club_a.pk, self.club_b.pk])

    def test_apply_with_multiple_candidates(self):
        self.client.force_login(self.user_a)
        response = self.client.post(self.request_url(), {
            "candidate_dates": [self.day1.isoformat(), self.day2.isoformat()],
            "venue": "opponent_dummy",
        })
        self.assertEqual(response.status_code, 200)   # 会場の選択肢が正しくない

        facility_free_venue = "opponent"
        Availability.objects.filter(club=self.club_b).update(can_host=True)
        response = self.client.post(self.request_url(), {
            "candidate_dates": [self.day2.isoformat(), self.day1.isoformat(), self.day1.isoformat()],
            "venue": facility_free_venue,
            "message": "よろしくお願いします",
        })
        self.assertRedirects(response, reverse("sent_matches"))
        match = PracticeMatch.objects.get(status="pending")
        self.assertIsNone(match.date)
        self.assertEqual([c.date for c in match.candidates.all()], [self.day1, self.day2])

        # 申し込みの会話が作られ、備考が最初のメッセージになっている
        conversation = match.conversation
        self.assertEqual(conversation.kind, Conversation.Kind.PROPOSAL)
        self.assertEqual(conversation.messages.get().content, "よろしくお願いします")

    def test_school_venue_needs_host_on_every_candidate(self):
        self.client.force_login(self.user_a)
        # A高校は day1 だけ受け入れ可。day2 も候補にすると、自校を会場にできない
        response = self.client.post(self.request_url(), {
            "candidate_dates": [self.day1.isoformat(), self.day2.isoformat()],
            "venue": "applicant",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "自校が「受け入れ可」になっていません")
        self.assertFalse(PracticeMatch.objects.filter(status="pending").exists())

    def test_candidate_rules(self):
        self.client.force_login(self.user_a)
        response = self.client.post(self.request_url(), {"candidate_dates": [], "venue": "applicant"})
        self.assertContains(response, "候補日を1日以上選んでください")

        past = (self.today - timedelta(days=1)).isoformat()
        response = self.client.post(self.request_url(), {"candidate_dates": [past], "venue": "applicant"})
        self.assertContains(response, "過去の日付は候補日にできません")

        many = [(self.today + timedelta(days=20 + i)).isoformat() for i in range(6)]
        response = self.client.post(self.request_url(), {"candidate_dates": many, "venue": "applicant"})
        self.assertContains(response, "候補日は5日までにしてください")

    def test_schedule_link_prechecks_dates(self):
        self.client.force_login(self.user_a)
        response = self.client.get(self.request_url() + f"?date={self.day1}&date={self.day2}")
        checked = [c["date"] for c in response.context["common_dates"] if c["checked"]]
        self.assertEqual(checked, [self.day1, self.day2])

    def make_proposal(self):
        match = PracticeMatch.objects.create(
            applicant_club=self.club_a, opponent_club=self.club_b, venue_kind="opponent")
        c1 = CandidateDate.objects.create(match=match, date=self.day1)
        c2 = CandidateDate.objects.create(match=match, date=self.day2)
        return match, c1, c2

    def test_opponent_confirms_one_candidate(self):
        match, c1, c2 = self.make_proposal()
        self.client.force_login(self.user_b)
        response = self.client.get(reverse("received_matches"))
        self.assertEqual(response.context["pending"], [match])

        self.client.post(reverse("match_respond", args=[match.pk]),
                         {"action": "approve", "candidate_date_id": c2.pk})
        match.refresh_from_db()
        self.assertEqual((match.status, match.date), ("confirmed", self.day2))

    def test_confirm_requires_a_candidate(self):
        match, c1, c2 = self.make_proposal()
        self.client.force_login(self.user_b)
        self.client.post(reverse("match_respond", args=[match.pk]), {"action": "approve"})
        match.refresh_from_db()
        self.assertEqual(match.status, "pending")

    def test_cannot_confirm_on_busy_day(self):
        match, c1, c2 = self.make_proposal()
        # B高校は day1 に、C高校との試合がすでに確定している
        PracticeMatch.objects.create(
            applicant_club=self.club_c, opponent_club=self.club_b, date=self.day1,
            venue_kind="applicant", status="confirmed")
        self.client.force_login(self.user_b)
        self.client.post(reverse("match_respond", args=[match.pk]),
                         {"action": "approve", "candidate_date_id": c1.pk})
        match.refresh_from_db()
        self.assertEqual(match.status, "pending")

    def test_reject(self):
        match, c1, c2 = self.make_proposal()
        self.client.force_login(self.user_b)
        self.client.post(reverse("match_respond", args=[match.pk]), {"action": "reject"})
        match.refresh_from_db()
        self.assertEqual(match.status, "declined")

    def test_only_opponent_can_respond(self):
        match, c1, c2 = self.make_proposal()
        for user in (self.user_a, self.user_c):
            self.client.force_login(user)
            response = self.client.post(reverse("match_respond", args=[match.pk]),
                                        {"action": "approve", "candidate_date_id": c1.pk})
            self.assertEqual(response.status_code, 404)

    def test_duplicate_candidate_with_same_opponent_is_rejected(self):
        self.make_proposal()
        self.client.force_login(self.user_a)
        response = self.client.post(self.request_url(), {
            "candidate_dates": [self.day1.isoformat()], "venue": "applicant"})
        self.assertContains(response, "すでに申し込み中")


class ResultTest(MatchingFeatureTestBase):
    """試合結果：各校が自校の得点と備考だけを入力する"""

    def test_each_school_enters_own_score(self):
        url = reverse("match_result_edit", args=[self.past_match.pk])

        self.client.force_login(self.user_a)          # 申込側
        self.client.post(url, {"my_score": 3, "my_notes": "A高校の備考"})
        result = MatchResult.objects.get(match=self.past_match)
        self.assertEqual((result.applicant_score, result.opponent_score), (3, None))
        self.assertIsNone(result.outcome_for(self.school_a))   # 相手校の入力待ち

        self.client.force_login(self.user_b)          # 相手側
        response = self.client.get(url)
        self.assertEqual(response.context["their_score"], 3)
        self.client.post(url, {"my_score": 1, "my_notes": "B高校の備考"})
        result.refresh_from_db()
        self.assertEqual((result.applicant_score, result.opponent_score), (3, 1))
        self.assertEqual((result.applicant_notes, result.opponent_notes), ("A高校の備考", "B高校の備考"))

        response = self.client.get(reverse("match_results"))
        row = response.context["results"][0]
        self.assertEqual((row["my_score"], row["their_score"], row["outcome"]), (1, 3, "lose"))
        self.assertEqual(row["my_notes"], "B高校の備考")

        self.client.force_login(self.user_a)
        response = self.client.get(reverse("match_results"))
        self.assertEqual(response.context["record"], {"win": 1, "lose": 0, "draw": 0})

    def test_planned_hides_button_after_own_score(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("planned_matches"))
        self.assertTrue(response.context["past"][0]["needs_my_score"])
        MatchResult.objects.create(match=self.past_match, applicant_score=2)
        response = self.client.get(reverse("planned_matches"))
        self.assertFalse(response.context["past"][0]["needs_my_score"])

    def test_cannot_record_before_match_day(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("match_result_edit", args=[self.future_match.pk]))
        self.assertRedirects(response, reverse("planned_matches"))

    def test_negative_score_is_rejected(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("match_result_edit", args=[self.past_match.pk]),
                                    {"my_score": -1})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MatchResult.objects.exists())

    def test_cancel_only_clears_own_side(self):
        result = MatchResult.objects.create(match=self.past_match, applicant_score=3, opponent_score=1)
        self.client.force_login(self.user_b)
        self.client.post(reverse("match_result_delete", args=[result.pk]))
        result.refresh_from_db()
        self.assertEqual((result.applicant_score, result.opponent_score), (3, None))

        self.client.force_login(self.user_a)
        self.client.post(reverse("match_result_delete", args=[result.pk]))
        self.assertFalse(MatchResult.objects.exists())

    def test_other_school_cannot_touch_result(self):
        result = MatchResult.objects.create(match=self.past_match, applicant_score=1)
        self.client.force_login(self.user_c)
        self.assertEqual(self.client.get(reverse("match_result_edit", args=[self.past_match.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("match_result_delete", args=[result.pk])).status_code, 404)


class ConversationTest(MatchingFeatureTestBase):
    """メッセージ：部活動の組み合わせごとの会話と、申し込みごとの会話"""

    def test_start_free_conversation_and_reuse_it(self):
        self.client.force_login(self.user_a)
        data = {"my_club": self.club_a.pk, "opponent_club": self.club_b.pk}
        response = self.client.post(reverse("message_start"), data)
        conversation = Conversation.objects.get()
        self.assertRedirects(response, reverse("message_room", args=[conversation.pk]))
        self.assertEqual(conversation.kind, Conversation.Kind.FREE)

        # 相手側から同じ組み合わせで始めても、同じ会話が開く
        self.client.force_login(self.user_b)
        self.client.post(reverse("message_start"), {"my_club": self.club_b.pk, "opponent_club": self.club_a.pk})
        self.assertEqual(Conversation.objects.count(), 1)

    def test_cannot_start_with_other_schools_club(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("message_start"),
                                    {"my_club": self.club_b.pk, "opponent_club": self.club_c.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Conversation.objects.exists())

    def test_send_and_read(self):
        conversation = Conversation.free_between(self.club_a, self.club_b)
        self.client.force_login(self.user_a)
        self.client.post(reverse("message_room", args=[conversation.pk]), {"content": "こんにちは"})
        message = Message.objects.get()
        self.assertEqual((message.sender, message.is_read), (self.school_a, False))

        self.client.force_login(self.user_b)
        response = self.client.get(reverse("teacher_home"))
        self.assertContains(response, 'class="sidebar-badge"')
        response = self.client.get(reverse("message_list"))
        self.assertEqual(response.context["conversations"][0]["unread"], 1)
        self.client.get(reverse("message_room", args=[conversation.pk]))
        message.refresh_from_db()
        self.assertTrue(message.is_read)

    def test_outsider_cannot_open_conversation(self):
        conversation = Conversation.free_between(self.club_a, self.club_b)
        self.client.force_login(self.user_c)
        self.assertEqual(self.client.get(reverse("message_room", args=[conversation.pk])).status_code, 404)

    def test_blank_message_is_rejected(self):
        conversation = Conversation.free_between(self.club_a, self.club_b)
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("message_room", args=[conversation.pk]), {"content": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Message.objects.exists())

    def test_match_conversation_link_creates_conversation_for_old_match(self):
        self.client.force_login(self.user_b)
        response = self.client.get(reverse("match_conversation", args=[self.past_match.pk]))
        conversation = Conversation.objects.get(match=self.past_match)
        self.assertRedirects(response, reverse("message_room", args=[conversation.pk]))

        self.client.force_login(self.user_c)
        self.assertEqual(self.client.get(reverse("match_conversation", args=[self.past_match.pk])).status_code, 404)


class ScheduleTest(MatchingFeatureTestBase):

    def test_common_dates_and_apply_links(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("schedule") + f"?club={self.club_a.pk}&opponent={self.club_b.pk}")
        self.assertEqual([c["date"] for c in response.context["candidates"]], [self.day1, self.day2])
        link = reverse("match_request", args=[self.club_a.pk, self.club_b.pk])
        self.assertContains(response, f"{link}?date={self.day1}")
        self.assertEqual(response.context["apply_all_url"], f"{link}?date={self.day1}&date={self.day2}")

    def test_pending_candidate_is_marked(self):
        match = PracticeMatch.objects.create(applicant_club=self.club_b, opponent_club=self.club_a, venue_kind="applicant")
        CandidateDate.objects.create(match=match, date=self.day1)
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("schedule") + f"?club={self.club_a.pk}&opponent={self.club_b.pk}")
        self.assertEqual(response.context["candidates"][0]["requested"], "申込中")
        self.assertEqual(response.context["apply_all_url"],
                         reverse("match_request", args=[self.club_a.pk, self.club_b.pk]) + f"?date={self.day2}")

    def test_other_schools_club_cannot_be_selected(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("schedule") + f"?club={self.club_b.pk}")
        self.assertIsNone(response.context["selected_club"])


class SportIconTest(TestCase):

    def test_icon_is_required_on_form_and_shown(self):
        board = User.objects.create_user(username="board", password="x", role="board")
        self.client.force_login(board)
        response = self.client.post(reverse("sport_add"), {"name": "テニス", "icon": ""})
        self.assertEqual(response.status_code, 200)
        self.client.post(reverse("sport_add"), {"name": "テニス", "icon": "🎾"})
        response = self.client.get(reverse("sport_list"))
        self.assertContains(response, "🎾")

    def test_default_icon_for_old_sports(self):
        self.assertEqual(Sport(name="野球").display_icon, "🏅")
