from datetime import timedelta

from django.test import TestCase
from django.urls import reverse

from accounts.testing import make_school
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
        cls.school = make_school(
            name="A高校", code="a_school", address="札幌市中央区", latitude=43.06, longitude=141.35)
        cls.other = make_school(
            name="B高校", code="b_school", address="札幌市北区", latitude=43.09, longitude=141.34)

        cls.club = Club.objects.create(school=cls.school, sport=cls.sport, gender="male", code="soccer_m")
        cls.other_club = Club.objects.create(school=cls.other, sport=cls.sport, gender="male", code="soccer_m")
        cls.teacher = User.objects.create_user(
            username="club_a", password="pass12345!", role=User.Role.CLUB, club=cls.club)
        User.objects.create_user(
            username="club_b", password="pass12345!", role=User.Role.CLUB, club=cls.other_club)

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
        a = make_school(name="A高校", code="a", address="札幌市", latitude=43.0, longitude=141.0)
        b = make_school(name="B高校", code="b", address="札幌市", latitude=43.1, longitude=141.1)
        cls.soccer_a = Club.objects.create(school=a, sport=soccer, gender="male", code="soccer")
        cls.tennis_a = Club.objects.create(school=a, sport=tennis, gender="male", code="tennis")
        cls.soccer_b = Club.objects.create(school=b, sport=soccer, gender="male", code="soccer")
        cls.soccer_user = User.objects.create_user(
            username="s", password="x", role=User.Role.CLUB, club=cls.soccer_a)
        cls.tennis_user = User.objects.create_user(
            username="t", password="x", role=User.Role.CLUB, club=cls.tennis_a)
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
        cls.school = make_school(
            name="A高校", code="a_school", address="札幌市", latitude=43.0, longitude=141.0)
        cls.club = Club.objects.create(school=cls.school, sport=cls.sport, gender="male", code="soccer_m")
        cls.teacher = User.objects.create_user(
            username="club_a", password="pass12345!", role=User.Role.CLUB, club=cls.club)
        cls.facility = Facility.objects.create(name="市民グラウンド", address="札幌市")
        cls.facility.sports.add(cls.sport)

    def setUp(self):
        self.client.force_login(self.board)

    def test_pages_render(self):
        urls = [reverse(name) for name in [
            "board_home", "school_account_list", "school_account_add",
            "school_list", "school_add", "sport_list", "sport_add", "club_list",
            "facility_list", "facility_add"]]
        account = self.school.account
        urls += [
            reverse("club_list") + f"?sport={self.sport.pk}&gender=male",
            reverse("school_account_edit", args=[account.pk]),
            reverse("school_account_toggle", args=[account.pk]),
            reverse("school_account_delete", args=[account.pk]),
            reverse("school_edit", args=[self.school.pk]),
            reverse("school_delete", args=[self.school.pk]),
            reverse("sport_edit", args=[self.sport.pk]),
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
        # 一覧に、削除できない理由が出て、削除ボタンは出ない
        response = self.client.get(reverse("sport_list"))
        self.assertContains(response, "部活動で使われています（1件）")
        self.assertNotContains(response, reverse("sport_delete", args=[self.sport.pk]))
        self.assertContains(response, reverse("sport_delete", args=[self.unused_sport.pk]))

        self.client.post(reverse("sport_delete", args=[self.sport.pk]))
        self.assertTrue(Sport.objects.filter(pk=self.sport.pk).exists())
        self.assertRedirects(self.client.post(reverse("sport_delete", args=[self.unused_sport.pk])),
                             reverse("sport_list"))
        self.assertFalse(Sport.objects.filter(pk=self.unused_sport.pk).exists())

    def test_sport_used_as_school_sport_cannot_be_deleted(self):
        self.school.sports.add(self.unused_sport)
        self.client.post(reverse("sport_delete", args=[self.unused_sport.pk]))
        self.assertTrue(Sport.objects.filter(pk=self.unused_sport.pk).exists())

    def test_school_account_create_edit_toggle_delete(self):
        # 作成：学校ID＋パスワード（学校情報はまだない）
        data = {"account_id": "b_school", "password": "Practice-2026!", "password_confirm": "Practice-2026!"}
        self.assertRedirects(self.client.post(reverse("school_account_add"), data), reverse("school_account_list"))
        account = User.objects.get(username="b_school")
        self.assertEqual(account.role, User.Role.SCHOOL)
        self.assertTrue(account.check_password("Practice-2026!"))
        response = self.client.get(reverse("school_account_list"))
        self.assertContains(response, "未登録")
        self.assertContains(response, "a_school")

        # 同じ学校IDは作れない・パスワードの確認が違えば作れない
        response = self.client.post(reverse("school_account_add"), data)
        self.assertContains(response, "この学校IDはすでに使われています。")
        response = self.client.post(reverse("school_account_add"), {**data, "account_id": "c", "password_confirm": "x"})
        self.assertContains(response, "パスワードが一致しません。")

        # 編集：パスワードが空欄なら変えない
        url = reverse("school_account_edit", args=[account.pk])
        self.client.post(url, {"account_id": "b_school2", "password": "", "password_confirm": ""})
        account.refresh_from_db()
        self.assertEqual(account.username, "b_school2")
        self.assertTrue(account.check_password("Practice-2026!"))

        # 利用停止（確認画面のあと）
        url = reverse("school_account_toggle", args=[account.pk])
        self.assertContains(self.client.get(url), "利用停止にしますか")
        self.assertRedirects(self.client.post(url), reverse("school_account_list"))
        account.refresh_from_db()
        self.assertFalse(account.is_active)

        # 削除（学校情報がなければ削除できる）
        url = reverse("school_account_delete", args=[account.pk])
        self.assertContains(self.client.get(url), "本当に削除しますか")
        self.assertRedirects(self.client.post(url), reverse("school_account_list"))
        self.assertFalse(User.objects.filter(pk=account.pk).exists())

    def test_school_account_with_school_info_cannot_be_deleted(self):
        url = reverse("school_account_delete", args=[self.school.account.pk])
        self.assertContains(self.client.get(url), "学校情報が登録されているため")
        self.client.post(url)
        self.assertTrue(User.objects.filter(pk=self.school.account.pk).exists())

    def test_school_info_create_edit_delete(self):
        from unittest import mock
        account = User.objects.create_user(username="b_school", password="x", role=User.Role.SCHOOL)
        data = {"account_id": "b_school", "name": "B高校", "address": "札幌市北区", "phone": "011-000-0000"}
        with mock.patch("schools.forms.geocode", return_value=(43.1, 141.3)):
            # 学校アカウントのない学校IDでは登録できない
            response = self.client.post(reverse("school_add"), {**data, "account_id": "nobody"})
            self.assertContains(response, "この学校IDの学校アカウントがありません")
            self.assertRedirects(self.client.post(reverse("school_add"), data), reverse("school_list"))
            school = School.objects.get(account=account)
            self.assertEqual((school.name, school.phone, school.latitude), ("B高校", "011-000-0000", 43.1))
            # 同じ学校IDの学校情報は2つ作れない
            response = self.client.post(reverse("school_add"), {**data, "name": "C高校"})
            self.assertContains(response, "この学校IDの学校情報は、すでに登録されています。")

            self.client.post(reverse("school_edit", args=[school.pk]),
                             {"name": "B高等学校", "address": "札幌市北区", "phone": ""})
            school.refresh_from_db()
            self.assertEqual((school.name, school.phone), ("B高等学校", ""))

        response = self.client.get(reverse("school_list"))
        self.assertContains(response, "B高等学校")
        self.assertContains(response, "b_school")

        # 部活動のある学校情報は削除できない。ない学校情報は削除できる
        response = self.client.get(reverse("school_delete", args=[self.school.pk]))
        self.assertContains(response, "部活動が登録されています（1件）")
        self.client.post(reverse("school_delete", args=[self.school.pk]))
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())
        self.assertRedirects(self.client.post(reverse("school_delete", args=[school.pk])), reverse("school_list"))
        self.assertFalse(School.objects.filter(pk=school.pk).exists())

    def test_admin_account_create(self):
        url = reverse("admin_account_create")
        data = {"account_id": "board2", "password": "Practice-2026!", "password_confirm": "Practice-2026!"}
        self.assertRedirects(self.client.post(url, data), reverse("board_home"))
        self.assertEqual(User.objects.get(username="board2").role, User.Role.BOARD)
        self.assertContains(self.client.post(url, data), "この管理者IDはすでに使われています。")

        # ログインしていない人・部活動は、管理者アカウントを作れない
        self.client.logout()
        self.client.post(url, {**data, "account_id": "board3"})
        self.client.force_login(self.teacher)
        self.client.post(url, {**data, "account_id": "board3"})
        self.assertFalse(User.objects.filter(username="board3").exists())

    def test_sport_edit(self):
        response = self.client.post(reverse("sport_edit", args=[self.sport.pk]), {"name": "フットボール", "icon": "⚽"})
        self.assertRedirects(response, reverse("sport_list"))
        self.sport.refresh_from_db()
        self.assertEqual(self.sport.name, "フットボール")
        response = self.client.post(reverse("sport_edit", args=[self.sport.pk]), {"name": "", "icon": "⚽"})
        self.assertContains(response, "を入力してください。")

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
        response = client.post(reverse("board_login"), {"account_id": "board", "password": "x"}, follow=True)
        self.assertRedirects(response, reverse("entry"))
        self.assertContains(response, "ログイン状態が変わったため、送信できませんでした")


class LoginPageTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sport = Sport.objects.create(name="サッカー")
        cls.school = make_school(name="A高校", code="a_school", password="school-pass1", address="札幌市")
        other = make_school(name="B高校", code="b_school", address="札幌市")
        cls.club = Club.objects.create(school=cls.school, sport=cls.sport, gender="male", code="soccer")
        cls.other_club = Club.objects.create(school=other, sport=cls.sport, gender="male", code="soccer")
        cls.teacher = User.objects.create_user(
            username="club_a", password="pass12345!", role=User.Role.CLUB, club=cls.club)
        User.objects.create_user(
            username="club_b", password="other12345!", role=User.Role.CLUB, club=cls.other_club)
        cls.advisor = User.objects.create_user(
            username="t1", password="advisor-pass1", role=User.Role.TEACHER, school=cls.school, advisor_name="山田")
        cls.board = User.objects.create_user(username="board", password="pass12345!", role=User.Role.BOARD)

    def login(self, school_id, club_id, password):
        return self.client.post(reverse("login"), {
            "school_id": school_id, "club_id": club_id, "password": password})

    def assertLoggedInAs(self, user):
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def assertNotLoggedIn(self):
        self.assertNotIn("_auth_user_id", self.client.session)

    # ---------- 入口 ----------

    def test_entry_routes_by_account_id(self):
        response = self.client.post(reverse("entry"), {"account_id": "board"})
        self.assertRedirects(response, reverse("board_login") + "?account_id=board")
        response = self.client.post(reverse("entry"), {"account_id": "a_school"})
        self.assertRedirects(response, reverse("login") + "?school_id=a_school")
        # 学校IDが入力欄に入っている
        self.assertContains(self.client.get(reverse("login") + "?school_id=a_school"), 'value="a_school"')
        response = self.client.post(reverse("entry"), {"account_id": "nobody"})
        self.assertContains(response, "このIDのアカウントは見つかりませんでした。")
        response = self.client.post(reverse("entry"), {"account_id": ""})
        self.assertContains(response, "アカウントIDを入力してください。")

    def test_top_page_is_entry(self):
        response = self.client.get("/")
        self.assertContains(response, "entry-page")
        self.assertContains(response, reverse("club_account_register"))

    # ---------- 学校側ログイン（部活動） ----------

    def test_club_login_with_school_and_club_ids(self):
        response = self.login("a_school", "soccer", "pass12345!")
        self.assertRedirects(response, reverse("teacher_home"))
        self.assertLoggedInAs(self.teacher)

    def test_same_club_id_in_other_school_is_a_different_account(self):
        # 部活IDが同じでも、学校IDで区別される（B高校のパスワードではA高校に入れない）
        response = self.login("a_school", "soccer", "other12345!")
        self.assertContains(response, "学校ID・部活ID・パスワードのいずれかが正しくありません。")
        self.assertNotLoggedIn()

    def test_inactive_club_cannot_login(self):
        User.objects.filter(pk=self.teacher.pk).update(is_active=False)
        response = self.login("a_school", "soccer", "pass12345!")
        self.assertNotLoggedIn()
        self.assertContains(response, "正しくありません")

    def test_stopped_school_blocks_club_and_advisor(self):
        # 学校アカウントを利用停止にすると、その学校の部活動・顧問もログインできない
        User.objects.filter(pk=self.school.account_id).update(is_active=False)
        self.login("a_school", "soccer", "pass12345!")
        self.assertNotLoggedIn()
        self.client.post(reverse("advisor_login"), {"school_id": "a_school", "name": "山田", "password": "advisor-pass1"})
        self.assertNotLoggedIn()

    def test_empty_fields_show_which_is_missing(self):
        cases = [
            ({"school_id": "", "club_id": "", "password": ""}, "学校ID・部活ID・パスワードを入力してください。"),
            ({"school_id": "a_school", "club_id": "", "password": ""}, "部活IDとパスワードを入力してください。"),
            ({"school_id": "a_school", "club_id": "soccer", "password": ""}, "パスワードを入力してください。"),
            ({"school_id": "", "club_id": "soccer", "password": "x"}, "学校IDを入力してください。"),
        ]
        for data, message in cases:
            with self.subTest(data=data):
                response = self.client.post(reverse("login"), data)
                self.assertContains(response, message)

    def test_wrong_password_shows_error_and_keeps_id(self):
        response = self.login("nobody", "soccer", "x")
        self.assertContains(response, "学校ID・部活ID・パスワードのいずれかが正しくありません。")
        self.assertContains(response, 'value="nobody"')
        self.assertContains(response, 'value="soccer"')

    def test_login_pages_render_with_design(self):
        for name, css in [("entry", "entry-page"), ("login", "school-login"), ("advisor_login", "school-login"),
                          ("advisor_register", "school-login"), ("club_account_register", "school-login"),
                          ("board_login", "admin-login-page")]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, css)
                self.assertContains(response, "novalidate")   # ブラウザのチェックではなく、サーバーのエラーを出す

    # ---------- 管理者ログイン ----------

    def test_board_login(self):
        response = self.client.post(reverse("board_login"), {"account_id": "board", "password": "pass12345!"})
        self.assertRedirects(response, reverse("board_home"))

    def test_other_accounts_cannot_use_board_login(self):
        for username, password in [("club_a", "pass12345!"), ("t1", "advisor-pass1")]:
            response = self.client.post(reverse("board_login"), {"account_id": username, "password": password})
            self.assertContains(response, "管理者IDまたはパスワードが正しくありません。")
            self.assertNotLoggedIn()

    # ---------- 顧問 ----------

    def test_advisor_register_login_and_create_club(self):
        url = reverse("advisor_register")
        data = {"school_id": "a_school", "school_password": "school-pass1", "name": "佐藤",
                "password": "Practice-2026!", "password_confirm": "Practice-2026!"}
        # 学校パスワードが違えば登録できない
        response = self.client.post(url, {**data, "school_password": "wrong"})
        self.assertContains(response, "学校IDまたは学校パスワードが正しくありません。")
        # 同じ学校で同じ顧問名は登録できない
        response = self.client.post(url, {**data, "name": "山田"})
        self.assertContains(response, "この顧問名は、この学校ですでに登録されています。")

        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("advisor_login") + "?school_id=a_school")
        advisor = User.objects.get(advisor_name="佐藤")
        self.assertEqual((advisor.role, advisor.school), (User.Role.TEACHER, self.school))

        response = self.client.post(reverse("advisor_login"),
                                    {"school_id": "a_school", "name": "佐藤", "password": "Practice-2026!"})
        self.assertRedirects(response, reverse("advisor_home"))
        self.assertLoggedInAs(advisor)

        # 部活動管理：部活動（競技・男女区分・部活ID）を登録する
        tennis = Sport.objects.create(name="テニス")
        response = self.client.post(reverse("advisor_club_list"),
                                    {"sport": tennis.pk, "gender": "female", "code": "tennis_f"})
        self.assertRedirects(response, reverse("advisor_club_list"))
        club = Club.objects.get(school=self.school, code="tennis_f")
        # 同じ部活ID・同じ競技と区分は登録できない
        response = self.client.post(reverse("advisor_club_list"),
                                    {"sport": tennis.pk, "gender": "male", "code": "tennis_f"})
        self.assertContains(response, "この部活IDは、この学校ですでに使われています。")
        response = self.client.post(reverse("advisor_club_list"),
                                    {"sport": tennis.pk, "gender": "female", "code": "other"})
        self.assertContains(response, "この競技・男女区分の部活動は、すでに登録されています。")
        response = self.client.get(reverse("advisor_club_list"))
        self.assertContains(response, "tennis_f")
        self.assertContains(response, "未登録")

        # 編集・削除
        self.client.post(reverse("advisor_club_edit", args=[club.pk]),
                         {"sport": tennis.pk, "gender": "mixed", "code": "tennis"})
        club.refresh_from_db()
        self.assertEqual((club.gender, club.code), ("mixed", "tennis"))
        self.client.post(reverse("advisor_club_delete", args=[club.pk]))
        self.assertFalse(Club.objects.filter(pk=club.pk).exists())

    def test_advisor_school_profile_sports(self):
        self.client.force_login(self.advisor)
        response = self.client.get(reverse("advisor_school"))
        self.assertContains(response, "A高校")
        self.assertContains(response, "a_school")
        tennis = Sport.objects.create(name="テニス")
        response = self.client.post(reverse("advisor_school"), {"sports": [self.sport.pk, tennis.pk]})
        self.assertRedirects(response, reverse("advisor_school"))
        self.assertEqual(set(self.school.sports.all()), {self.sport, tennis})
        # 学校名などは、顧問の画面からは変わらない
        self.client.post(reverse("advisor_school"), {"sports": [], "name": "Z高校"})
        self.school.refresh_from_db()
        self.assertEqual((self.school.name, self.school.sports.count()), ("A高校", 0))

    def test_advisor_cannot_touch_other_schools_clubs(self):
        self.client.force_login(self.advisor)
        self.assertEqual(self.client.get(reverse("advisor_club_edit", args=[self.other_club.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("advisor_club_delete", args=[self.other_club.pk])).status_code, 404)
        # 顧問は練習試合の画面を開けない（部活動のアカウントで操作する）
        response = self.client.get(reverse("received_matches"), follow=True)
        self.assertRedirects(response, reverse("advisor_home"))

    # ---------- 部活動アカウントの新規登録 ----------

    def test_club_account_register_once(self):
        club = Club.objects.create(school=self.school, sport=self.sport, gender="female", code="soccer_f")
        url = reverse("club_account_register")
        data = {"school_id": "a_school", "login_id": "soccer_f",
                "password": "Practice-2026!", "password_confirm": "Practice-2026!"}
        # 顧問が作っていない部活IDは登録できない
        response = self.client.post(url, {**data, "login_id": "nothing"})
        self.assertContains(response, "学校IDと部活IDの組み合わせが見つかりません。")

        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("login") + "?school_id=a_school&club_id=soccer_f")
        self.assertEqual(User.objects.get(club=club).role, User.Role.CLUB)
        self.assertRedirects(self.login("a_school", "soccer_f", "Practice-2026!"), reverse("teacher_home"))

        # 一度登録した部活動は、もう登録できない
        self.client.logout()
        response = self.client.post(url, data)
        self.assertContains(response, "この部活動のアカウントは、すでに登録されています。")

    def test_advisor_can_reset_club_account(self):
        self.client.force_login(self.advisor)
        self.client.post(reverse("advisor_club_account_reset", args=[self.club.pk]))
        self.assertFalse(User.objects.filter(club=self.club).exists())
        self.assertTrue(Club.objects.filter(pk=self.club.pk).exists())
