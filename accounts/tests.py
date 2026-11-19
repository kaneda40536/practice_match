from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from facilities.models import Facility
from matching.models import Availability, CandidateDate, Conversation, Message, PracticeMatch
from schools.models import Area, Club, School, Sport
from .models import User


class TeacherPagesTest(TestCase):
    """顧問の画面が、エラーなく表示されるかを確認する（画面の作り直し後の動作確認用）"""

    @classmethod
    def setUpTestData(cls):
        area = Area.objects.create(name="札幌地区")
        cls.sport = Sport.objects.create(name="サッカー")
        cls.school = School.objects.create(
            name="A高校", area=area, address="札幌市中央区", latitude=43.06, longitude=141.35)
        cls.other = School.objects.create(
            name="B高校", area=area, address="札幌市北区", latitude=43.09, longitude=141.34)
        cls.teacher = User.objects.create_user(
            username="a_school", password="pass12345!", role=User.Role.TEACHER, school=cls.school)
        User.objects.create_user(
            username="b_school", password="pass12345!", role=User.Role.TEACHER, school=cls.other)

        cls.club = Club.objects.create(school=cls.school, sport=cls.sport, gender="male")
        cls.other_club = Club.objects.create(school=cls.other, sport=cls.sport, gender="male")

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
            reverse("my_club_list"),
            reverse("my_club_delete", args=[self.club.pk]),
            reverse("club_availability", args=[self.club.pk]),
            reverse("opponent_search"),
            reverse("opponent_search") + f"?club={self.club.pk}",
            reverse("opponent_search") + f"?club={self.club.pk}&level=higher",
            reverse("opponent_detail", args=[self.club.pk, self.other_club.pk]),
            reverse("my_facility_list"),
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
            reverse("message_room", args=[self.legacy.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "admin-sidebar")

    def test_home_shows_sidebar_and_stats(self):
        response = self.client.get(reverse("teacher_home"))
        self.assertContains(response, "A高校")
        self.assertNotContains(response, "準備中")       # すべての機能が使える
        self.assertContains(response, reverse("received_matches"))

    def test_sidebar_marks_current_page(self):
        response = self.client.get(reverse("club_availability", args=[self.club.pk]))
        # 希望日の画面では「部活動管理」が光る
        self.assertContains(
            response, f'href="{reverse("my_club_list")}" class="sidebar-link active"')

    def test_add_club_from_list_page(self):
        tennis = Sport.objects.create(name="テニス")
        response = self.client.post(reverse("my_club_add"), {"sport": tennis.pk, "gender": "female"})
        self.assertRedirects(response, reverse("my_club_list"))
        self.assertTrue(Club.objects.filter(school=self.school, sport=tennis).exists())

    def test_add_duplicate_club_shows_error_on_list_page(self):
        response = self.client.post(reverse("my_club_add"), {"sport": self.sport.pk, "gender": "male"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "すでに登録されています")
        self.assertContains(response, "登録済みの部活動")   # 一覧も一緒に表示される


class BoardPagesTest(TestCase):
    """教育委員会の画面が、エラーなく表示されるかを確認する"""

    @classmethod
    def setUpTestData(cls):
        cls.board = User.objects.create_user(
            username="board", password="pass12345!", role=User.Role.BOARD)
        area = Area.objects.create(name="札幌地区")
        cls.sport = Sport.objects.create(name="サッカー")
        cls.unused_sport = Sport.objects.create(name="テニス")
        cls.school = School.objects.create(name="A高校", area=area, address="札幌市", latitude=43.0, longitude=141.0)
        cls.teacher = User.objects.create_user(
            username="a_school", password="pass12345!", role=User.Role.TEACHER, school=cls.school)
        Club.objects.create(school=cls.school, sport=cls.sport, gender="male")
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
            reverse("school_delete", args=[self.school.pk]),
            reverse("sport_edit", args=[self.sport.pk]),
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
        response = client.post(reverse("login"), {"username": "board", "password": "x"}, follow=True)
        self.assertRedirects(response, reverse("login"))
        self.assertContains(response, "ログイン状態が変わったため、送信できませんでした")


class LoginPageTest(TestCase):
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
            ({"username": "", "password": ""}, "学校IDとパスワードを入力してください。"),
            ({"username": "a_school", "password": ""}, "パスワードを入力してください。"),
            ({"username": "", "password": "x"}, "学校IDを入力してください。"),
        ]
        for data, message in cases:
            with self.subTest(data=data):
                response = self.client.post(reverse("login"), data)
                self.assertContains(response, message)

    def test_wrong_password_shows_error_and_keeps_id(self):
        response = self.client.post(reverse("login"), {"username": "nobody", "password": "x"})
        self.assertContains(response, "学校IDまたはパスワードが正しくありません。")
        self.assertContains(response, 'value="nobody"')
