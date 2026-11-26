from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from facilities.models import Facility
from matching.models import Availability, CandidateDate, Conversation, Message, PracticeMatch
from schools.models import Club, School, Sport
from .models import User


class TeacherPagesTest(TestCase):
    """顧問の画面が、エラーなく表示されるかを確認する（画面の作り直し後の動作確認用）"""

    @classmethod
    def setUpTestData(cls):
        cls.sport = Sport.objects.create(name="サッカー")
        cls.school = School.objects.create(
            name="A高校", code="a_school", address="札幌市中央区", latitude=43.06, longitude=141.35)
        cls.other = School.objects.create(
            name="B高校", code="b_school", address="札幌市北区", latitude=43.09, longitude=141.34)

        cls.club = Club.objects.create(school=cls.school, sport=cls.sport, gender="male", code="soccer_m")
        cls.other_club = Club.objects.create(school=cls.other, sport=cls.sport, gender="male", code="soccer_m")
        cls.teacher = User.objects.create_user(
            username="club_a", password="pass12345!", role=User.Role.TEACHER, club=cls.club)
        User.objects.create_user(
            username="club_b", password="pass12345!", role=User.Role.TEACHER, club=cls.other_club)

        facility = Facility.objects.create(
            name="市民グラウンド", address="札幌市", latitude=43.07, longitude=141.36)
        facility.sports.add(cls.sport)

        day = timezone.localdate() + timedelta(days=7)
        Availability.objects.create(club=cls.club, date=day, can_host=True)
        Availability.objects.create(club=cls.other_club, date=day, can_host=False)

        # 届いた申し込み（申込中・候補日2つ）と、申し込んだ試合（確定）
        received = PracticeMatch.objects.create(
            applicant_club=cls.other_club, opponent_club=cls.club,
            venue_kind=PracticeMatch.VenueKind.FACILITY, facility=facility, message="よろしくお願いします")
        CandidateDate.objects.create(match=received, date=day)
        CandidateDate.objects.create(match=received, date=day + timedelta(days=2))
        sent = PracticeMatch.objects.create(
            applicant_club=cls.club, opponent_club=cls.other_club, date=day + timedelta(days=1),
            venue_kind=PracticeMatch.VenueKind.APPLICANT, status=PracticeMatch.Status.CONFIRMED)
        CandidateDate.objects.create(match=sent, date=day + timedelta(days=1))

        # 申し込みの会話と、以前の会話（部活動の指定なし）
        Message.objects.create(conversation=Conversation.for_match(received), sender=cls.other, content="よろしく")
        cls.legacy = Conversation.objects.create(school_a=cls.school, school_b=cls.other)
        Message.objects.create(conversation=cls.legacy, sender=cls.school, content="以前のメッセージ")

    def setUp(self):
        self.client.force_login(self.teacher)

    def test_pages_render(self):
        urls = [
            reverse("teacher_home"),
            reverse("my_school"),
            reverse("club_availability", args=[self.club.pk]),
            reverse("opponent_search"),
            reverse("opponent_search") + f"?club={self.club.pk}",
            reverse("opponent_search") + f"?club={self.club.pk}&level=higher",
            reverse("opponent_detail", args=[self.club.pk, self.other_club.pk]),
            reverse("tournament_results"),
            reverse("match_request", args=[self.club.pk, self.other_club.pk]),
            reverse("received_matches"),
            reverse("sent_matches"),
            reverse("schedule"),
            reverse("schedule") + f"?club={self.club.pk}",
            reverse("schedule") + f"?club={self.club.pk}&opponent={self.other_club.pk}",
            reverse("planned_matches"),
            reverse("match_results"),
            reverse("message_list"),
            reverse("message_room", args=[Conversation.objects.get(match__isnull=False).pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "admin-sidebar")

    def test_home_shows_sidebar_and_stats(self):
        response = self.client.get(reverse("teacher_home"))
        self.assertContains(response, "A高校")
        self.assertContains(response, "男子サッカー部")
        self.assertNotContains(response, "準備中")       # すべての機能が使える
        self.assertContains(response, reverse("received_matches"))

    def test_sidebar_marks_current_page(self):
        response = self.client.get(reverse("club_availability", args=[self.club.pk]))
        # 希望日の画面では「日程調整」が光る
        self.assertContains(
            response, f'href="{reverse("schedule")}" class="sidebar-link active"')

    def test_schedule_and_search_use_own_club(self):
        # 部活動を選ばなくても、ログイン中の部活動で表示される
        response = self.client.get(reverse("schedule"))
        self.assertEqual(response.context["selected_club"], self.club)
        self.assertContains(response, reverse("club_availability", args=[self.club.pk]))
        response = self.client.get(reverse("opponent_search") + "?level=higher")
        self.assertEqual(response.context["selected_club"], self.club)
        self.assertContains(response, reverse("club_level", args=[self.club.pk]))

    def test_my_school_shows_login_ids(self):
        response = self.client.get(reverse("my_school"))
        self.assertContains(response, "a_school")
        self.assertContains(response, "soccer_m")

    def test_club_management_menu_is_gone(self):
        # 部活動は教育委員会がアカウントと一緒に作るので、部活動側のメニューにはない
        response = self.client.get(reverse("teacher_home"))
        self.assertNotContains(response, "部活動管理")

    def test_legacy_school_conversation_is_hidden(self):
        # 部活動を指定しない以前の会話（学校どうし）は、部活動のアカウントからは見られない
        self.assertEqual(self.client.get(reverse("message_room", args=[self.legacy.pk])).status_code, 404)


class ClubScopeTest(TestCase):
    """同じ学校でも、ほかの部活動の申し込み・試合・メッセージ・大会成績は見られない"""

    @classmethod
    def setUpTestData(cls):
        soccer = Sport.objects.create(name="サッカー")
        tennis = Sport.objects.create(name="テニス")
        a = School.objects.create(name="A高校", code="a", address="札幌市", latitude=43.0, longitude=141.0)
        b = School.objects.create(name="B高校", code="b", address="札幌市", latitude=43.1, longitude=141.1)
        cls.soccer_a = Club.objects.create(school=a, sport=soccer, gender="male", code="soccer")
        cls.tennis_a = Club.objects.create(school=a, sport=tennis, gender="male", code="tennis")
        cls.soccer_b = Club.objects.create(school=b, sport=soccer, gender="male", code="soccer")
        cls.soccer_user = User.objects.create_user(
            username="s", password="x", role=User.Role.TEACHER, club=cls.soccer_a)
        cls.tennis_user = User.objects.create_user(
            username="t", password="x", role=User.Role.TEACHER, club=cls.tennis_a)
        cls.match = PracticeMatch.objects.create(
            applicant_club=cls.soccer_b, opponent_club=cls.soccer_a, venue_kind="applicant")
        CandidateDate.objects.create(match=cls.match, date=timezone.localdate() + timedelta(days=5))
        Message.objects.create(conversation=Conversation.for_match(cls.match), sender=b, content="よろしく")

    def test_other_club_of_same_school_cannot_see(self):
        self.client.force_login(self.tennis_user)
        self.assertEqual(list(self.client.get(reverse("received_matches")).context["pending"]), [])
        self.assertEqual(self.client.get(reverse("message_list")).context["conversations"], [])
        self.assertEqual(self.client.post(reverse("match_respond", args=[self.match.pk]),
                                          {"action": "reject"}).status_code, 404)
        self.assertEqual(self.client.get(reverse("match_conversation", args=[self.match.pk])).status_code, 404)
        # ほかの部活動の希望日の画面も開けない
        self.assertEqual(self.client.get(
            reverse("club_availability", args=[self.soccer_a.pk])).status_code, 404)
        response = self.client.get(reverse("live_updates"))
        self.assertEqual(response.json()["badges"], {"unread_messages": 0, "pending_received": 0})

    def test_own_club_sees_it(self):
        self.client.force_login(self.soccer_user)
        self.assertEqual(list(self.client.get(reverse("received_matches")).context["pending"]), [self.match])
        response = self.client.get(reverse("live_updates"))
        self.assertEqual(response.json()["badges"], {"unread_messages": 1, "pending_received": 1})


class BoardPagesTest(TestCase):
    """教育委員会の画面が、エラーなく表示されるかを確認する"""

    @classmethod
    def setUpTestData(cls):
        cls.board = User.objects.create_user(
            username="board", password="pass12345!", role=User.Role.BOARD)
        cls.sport = Sport.objects.create(name="サッカー")
        cls.unused_sport = Sport.objects.create(name="テニス")
        cls.school = School.objects.create(
            name="A高校", code="a_school", address="札幌市", latitude=43.0, longitude=141.0)
        cls.club = Club.objects.create(school=cls.school, sport=cls.sport, gender="male", code="soccer_m")
        cls.teacher = User.objects.create_user(
            username="club_a", password="pass12345!", role=User.Role.TEACHER, club=cls.club)
        cls.facility = Facility.objects.create(name="市民グラウンド", address="札幌市")
        cls.facility.sports.add(cls.sport)

    def setUp(self):
        self.client.force_login(self.board)

    def test_pages_render(self):
        urls = [reverse(name) for name in [
            "board_home", "school_account_list", "school_account_add",
            "school_list", "sport_list", "sport_add", "club_list",
            "facility_list", "facility_add"]]
        urls += [
            reverse("club_list") + f"?sport={self.sport.pk}&gender=male",
            reverse("school_account_password", args=[self.teacher.pk]),
            reverse("school_edit", args=[self.school.pk]),
            reverse("school_account_delete", args=[self.teacher.pk]),
            reverse("sport_delete", args=[self.sport.pk]),
            reverse("facility_edit", args=[self.facility.pk]),
            reverse("facility_delete", args=[self.facility.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "admin-sidebar")
                self.assertContains(response, "ADMIN SYSTEM")

    def test_sport_in_use_cannot_be_deleted(self):
        response = self.client.get(reverse("sport_delete", args=[self.sport.pk]))
        self.assertContains(response, "この競技は削除できません。")
        self.assertNotContains(response, "削除する</button>")

        response = self.client.get(reverse("sport_delete", args=[self.unused_sport.pk]))
        self.assertContains(response, "削除する</button>")

    def test_toggle_account(self):
        response = self.client.post(reverse("school_account_toggle", args=[self.teacher.pk]))
        self.assertRedirects(response, reverse("school_account_list"))
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.is_active)

    def test_account_list_shows_login_ids(self):
        response = self.client.get(reverse("school_account_list"))
        self.assertContains(response, "a_school")
        self.assertContains(response, "soccer_m")
        self.assertContains(response, "男子サッカー部")

    def test_account_list_is_grouped_by_school(self):
        other = School.objects.create(name="B高校", code="b_school", address="札幌市")
        response = self.client.get(reverse("school_account_list"))
        schools = list(response.context["schools"])
        self.assertEqual(schools, [self.school, other])
        self.assertEqual(schools[0].account_clubs, [self.club])
        self.assertEqual(schools[1].account_clubs, [])     # アカウントのない学校も表示する
        self.assertContains(response, "部活動アカウントはありません")
        # 学校名・学校ID・部活動名・部活動ID と、再設定・利用停止・削除
        for text in ["A高校", "a_school", "男子サッカー部", "soccer_m", "パスワード再設定", "利用停止",
                     reverse("school_account_delete", args=[self.teacher.pk])]:
            self.assertContains(response, text)

    def test_delete_club_account(self):
        other = School.objects.create(name="B高校", code="b_school", address="札幌市")
        other_club = Club.objects.create(school=other, sport=self.sport, gender="male", code="soccer")
        match = PracticeMatch.objects.create(
            applicant_club=self.club, opponent_club=other_club, venue_kind="applicant")
        url = reverse("school_account_delete", args=[self.teacher.pk])
        response = self.client.get(url)
        self.assertContains(response, "削除すると元に戻せません")
        self.assertEqual(response.context["match_count"], 1)

        response = self.client.post(url)
        self.assertRedirects(response, reverse("school_account_list"))
        self.assertFalse(User.objects.filter(pk=self.teacher.pk).exists())
        self.assertFalse(Club.objects.filter(pk=self.club.pk).exists())
        self.assertFalse(PracticeMatch.objects.filter(pk=match.pk).exists())
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())   # 学校は残る

    def test_school_list_shows_clubs_and_only_edit(self):
        response = self.client.get(reverse("school_list"))
        self.assertContains(response, "A高校")
        self.assertContains(response, "札幌市")
        self.assertContains(response, "男子サッカー部")
        self.assertContains(response, reverse("school_edit", args=[self.school.pk]))
        self.assertNotContains(response, ">削除<")
        self.assertNotContains(response, "a_school")     # 学校IDは部活動アカウント管理に表示する

    def test_edit_school_name_and_address(self):
        response = self.client.post(reverse("school_edit", args=[self.school.pk]),
                                    {"name": "A高等学校", "address": "札幌市"})
        self.assertRedirects(response, reverse("school_list"))
        self.school.refresh_from_db()
        self.assertEqual((self.school.name, self.school.code), ("A高等学校", "a_school"))

    def test_sport_cannot_be_edited(self):
        response = self.client.get(reverse("sport_list"))
        self.assertNotContains(response, ">編集<")
        self.assertContains(response, reverse("sport_delete", args=[self.sport.pk]))

    def test_create_club_account(self):
        data = {"school": self.school.pk, "sport": self.unused_sport.pk, "gender": "female",
                "code": "tennis_f", "password1": "Practice-2026!", "password2": "Practice-2026!"}
        response = self.client.post(reverse("school_account_add"), data)
        self.assertRedirects(response, reverse("school_account_list"))
        user = User.objects.get(club__code="tennis_f")
        self.assertEqual((user.club.school, user.school, user.role), (self.school, self.school, "teacher"))
        self.assertTrue(user.check_password("Practice-2026!"))

        # 同じ学校で、同じ部活動ID・同じ競技と区分は作れない
        response = self.client.post(reverse("school_account_add"), {**data, "gender": "mixed"})
        self.assertContains(response, "この部活動IDは、この学校ですでに使われています。")
        response = self.client.post(reverse("school_account_add"), {**data, "code": "other"})
        self.assertContains(response, "同じ競技・区分の部活動がすでに登録されています。")
        response = self.client.post(reverse("school_account_add"), {**data, "code": "テニス"})
        self.assertContains(response, "半角英数字")
        self.assertEqual(User.objects.filter(role="teacher").count(), 2)

    def test_create_account_with_new_school(self):
        """学校を選ばなければ、新しい学校をその場で登録して、部活動アカウントを作る"""
        from unittest import mock
        data = {"school": "", "new_school_name": "B高校", "new_school_code": "b_school",
                "new_school_address": "札幌市北区", "sport": self.sport.pk, "gender": "male",
                "code": "soccer_m", "password1": "Practice-2026!", "password2": "Practice-2026!"}
        with mock.patch("schools.forms.geocode", return_value=(43.1, 141.3)):
            response = self.client.post(reverse("school_account_add"), data)
            self.assertRedirects(response, reverse("school_account_list"))
            school = School.objects.get(code="b_school")
            self.assertEqual((school.name, school.latitude, school.longitude), ("B高校", 43.1, 141.3))
            self.assertEqual(User.objects.get(club__school=school, club__code="soccer_m").school, school)

            # 学校IDは重ねられない・新しい学校の入力がなければ作れない
            response = self.client.post(reverse("school_account_add"), {**data, "new_school_name": "C高校"})
            self.assertContains(response, "この学校IDはすでに使われています。")
            response = self.client.post(reverse("school_account_add"), {
                **data, "new_school_name": "", "new_school_code": "", "new_school_address": ""})
            self.assertContains(response, "学校名を入力してください。")
            self.assertContains(response, "学校IDを入力してください。")
        self.assertEqual(School.objects.count(), 2)

    def test_teacher_cannot_open_board_pages(self):
        self.client.force_login(self.teacher)
        # 403 の画面ではなく、自分のホームに案内される
        response = self.client.get(reverse("school_account_list"), follow=True)
        self.assertRedirects(response, reverse("teacher_home"))
        self.assertContains(response, "では開けないため、ホームに移動しました")

    def test_board_opening_teacher_page_goes_to_board_home(self):
        response = self.client.get(reverse("received_matches"), follow=True)
        self.assertRedirects(response, reverse("board_home"))
        self.assertContains(response, "flash--warning")

    def test_csrf_failure_shows_guidance_instead_of_403(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.board)
        response = client.post(reverse("sport_add"), {"name": "野球", "icon": "⚾"}, follow=True)
        self.assertRedirects(response, reverse("board_home"))
        self.assertContains(response, "ログイン状態が変わったため、送信できませんでした")
        self.assertFalse(Sport.objects.filter(name="野球").exists())

        # ログインしていなければ、ログイン画面に案内する
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("board_login"), {"username": "board", "password": "x"}, follow=True)
        self.assertRedirects(response, reverse("login"))
        self.assertContains(response, "ログイン状態が変わったため、送信できませんでした")


class LoginPageTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        sport = Sport.objects.create(name="サッカー")
        school = School.objects.create(name="A高校", code="a_school", address="札幌市")
        other = School.objects.create(name="B高校", code="b_school", address="札幌市")
        cls.club = Club.objects.create(school=school, sport=sport, gender="male", code="soccer")
        cls.other_club = Club.objects.create(school=other, sport=sport, gender="male", code="soccer")
        cls.teacher = User.objects.create_user(
            username="club_a", password="pass12345!", role=User.Role.TEACHER, club=cls.club)
        User.objects.create_user(
            username="club_b", password="other12345!", role=User.Role.TEACHER, club=cls.other_club)
        cls.board = User.objects.create_user(username="board", password="pass12345!", role=User.Role.BOARD)

    def login(self, school_code, club_code, password):
        return self.client.post(reverse("login"), {
            "school_code": school_code, "club_code": club_code, "password": password})

    def test_club_login_with_school_and_club_ids(self):
        response = self.login("a_school", "soccer", "pass12345!")
        self.assertRedirects(response, reverse("teacher_home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.teacher.pk)

    def test_same_club_id_in_other_school_is_a_different_account(self):
        # 部活動IDが同じでも、学校IDで区別される（B高校のパスワードではA高校に入れない）
        response = self.login("a_school", "soccer", "other12345!")
        self.assertContains(response, "学校ID・部活動ID・パスワードのいずれかが正しくありません。")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_club_cannot_login(self):
        User.objects.filter(pk=self.teacher.pk).update(is_active=False)
        response = self.login("a_school", "soccer", "pass12345!")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "正しくありません")

    def test_board_uses_board_login(self):
        # 教育委員会は、管理者ID＋パスワードの画面からログインする
        self.assertContains(self.client.get(reverse("login")), reverse("board_login"))
        response = self.client.post(reverse("board_login"), {"username": "board", "password": "pass12345!"})
        self.assertRedirects(response, reverse("board_home"))

    def test_club_account_cannot_use_board_login(self):
        response = self.client.post(reverse("board_login"), {"username": "club_a", "password": "pass12345!"})
        self.assertContains(response, "管理者IDまたはパスワードが正しくありません。")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "admin-login-page")

    def test_forms_skip_browser_check(self):
        # ブラウザの「このフィールドを入力してください」ではなく、サーバーのエラーを出す
        response = self.client.get(reverse("login"))
        self.assertContains(response, "novalidate")

    def test_empty_fields_show_which_is_missing(self):
        cases = [
            ({"school_code": "", "club_code": "", "password": ""}, "学校ID・部活動ID・パスワードを入力してください。"),
            ({"school_code": "a_school", "club_code": "", "password": ""}, "部活動IDとパスワードを入力してください。"),
            ({"school_code": "a_school", "club_code": "soccer", "password": ""}, "パスワードを入力してください。"),
            ({"school_code": "", "club_code": "soccer", "password": "x"}, "学校IDを入力してください。"),
        ]
        for data, message in cases:
            with self.subTest(data=data):
                response = self.client.post(reverse("login"), data)
                self.assertContains(response, message)

    def test_wrong_password_shows_error_and_keeps_id(self):
        response = self.login("nobody", "soccer", "x")
        self.assertContains(response, "学校ID・部活動ID・パスワードのいずれかが正しくありません。")
        self.assertContains(response, 'value="nobody"')
        self.assertContains(response, 'value="soccer"')
