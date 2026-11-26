"""2026-11-18 のデザイン更新で追加した機能のテスト

会場（学校内の施設・未定・受けた側が決める）、会場管理、大会成績管理、
対戦相手検索の競技レベルとおすすめ順
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from facilities.models import Facility
from schools.forms import current_fiscal_year
from schools.models import Club, School, Sport, TournamentResult
from .models import Availability, MatchResult, PracticeMatch
from .tests import MatchingFeatureTestBase


class VenueTest(MatchingFeatureTestBase):
    """会場：学校内の施設・公共の施設・未定。受けた側が確定するときに会場を決める（変更もできる）"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.gym_b = Facility.objects.create(school=cls.school_b, name="第一体育館")
        cls.gym_b.sports.add(cls.sport)
        cls.public = Facility.objects.create(
            name="市民グラウンド", address="札幌市", latitude=43.05, longitude=141.05)
        cls.public.sports.add(cls.sport)
        cls.gym_c = Facility.objects.create(school=cls.school_c, name="C高校体育館")  # 関係のない学校の施設
        cls.gym_c.sports.add(cls.sport)

    def request(self, venue):
        return self.client.post(reverse("match_request", args=[self.club_a.pk, self.club_b.pk]), {
            "candidate_dates": [self.day1.isoformat()], "venue": venue})

    def test_venue_choices(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("match_request", args=[self.club_a.pk, self.club_b.pk]))
        self.assertContains(response, "未定（相手校に決めてもらう）")
        self.assertContains(response, "A高校で実施（施設は未登録）")   # A高校は施設を登録していない
        self.assertContains(response, f'value="facility:{self.gym_b.pk}"')
        self.assertContains(response, f'value="facility:{self.public.pk}"')
        self.assertNotContains(response, f'value="facility:{self.gym_c.pk}"')
        self.assertNotContains(response, 'value="opponent"')            # B高校は施設から選ぶ

    def test_undecided_then_opponent_chooses(self):
        self.client.force_login(self.user_a)
        self.assertRedirects(self.request("undecided"), reverse("sent_matches"))
        match = PracticeMatch.objects.get(status="pending")
        self.assertEqual(match.venue_name, "未定（相手校が決めます）")

        self.client.force_login(self.user_b)
        response = self.client.get(reverse("received_matches"))
        self.assertContains(response, "会場を「未定」にしています")
        self.client.post(reverse("match_respond", args=[match.pk]), {
            "action": "approve", "candidate_date_id": match.candidates.get().pk,
            "venue": f"facility:{self.public.pk}"})
        match.refresh_from_db()
        self.assertEqual((match.status, match.facility), ("confirmed", self.public))

    def test_school_facility_needs_host(self):
        self.client.force_login(self.user_a)
        response = self.request(f"facility:{self.gym_b.pk}")   # B高校は day1 が受け入れ可ではない
        self.assertContains(response, "相手校が「受け入れ可」になっていません")

        Availability.objects.filter(club=self.club_b, date=self.day1).update(can_host=True)
        self.assertRedirects(self.request(f"facility:{self.gym_b.pk}"), reverse("sent_matches"))
        match = PracticeMatch.objects.get(status="pending")
        self.assertEqual(match.host_club, self.club_b)
        self.assertEqual(match.venue_name, "B高校 第一体育館")

        # 受けた側には、申し込んだ側が選んだ会場が最初から選ばれている
        self.client.force_login(self.user_b)
        response = self.client.get(reverse("received_matches"))
        self.assertContains(response, f'value="facility:{self.gym_b.pk}" selected')

    def test_other_school_facility_is_rejected(self):
        self.client.force_login(self.user_a)
        response = self.request(f"facility:{self.gym_c.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PracticeMatch.objects.filter(status="pending").exists())


class BoardVenueTest(MatchingFeatureTestBase):
    """会場管理（教育委員会）"""

    def test_board_venue_management(self):
        """教育委員会の「会場管理」：公共の会場だけを管理する（学校の会場は一覧に出ない）"""
        school_gym = Facility.objects.create(school=self.school_a, name="A高校体育館")
        public = Facility.objects.create(name="市民体育館", address="札幌市")
        board = User.objects.create_user(username="board", password="x", role=User.Role.BOARD)
        self.client.force_login(board)

        response = self.client.get(reverse("facility_list"))
        self.assertContains(response, "<h1>会場管理</h1>", html=True)
        self.assertContains(response, "新しい会場を登録")
        self.assertEqual(list(response.context["facilities"]), [public])            # 管理するのは公共の会場
        self.assertNotContains(response, "A高校体育館")
        self.assertNotContains(response, "学校内の会場")
        self.assertContains(response, f'href="{reverse("facility_edit", args=[public.pk])}"')
        self.assertNotContains(response, f'href="{reverse("facility_edit", args=[school_gym.pk])}"')

        # 学校内の会場は、教育委員会の画面からは変更・削除できない
        self.assertEqual(self.client.get(reverse("facility_edit", args=[school_gym.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("facility_delete", args=[school_gym.pk])).status_code, 404)

        # サイドバーの名前も「会場管理」
        self.assertContains(response, "<span>会場管理</span>", html=True)
        self.assertNotContains(response, "施設情報管理")


class TournamentResultTest(MatchingFeatureTestBase):
    """大会成績管理"""

    def test_create_edit_delete(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("tournament_results"), {})
        self.assertContains(response, "大会名を入力してください。")

        data = {"tournament_name": "地区新人大会", "fiscal_year": current_fiscal_year(),
                "level": "district", "achievement": "champion"}
        self.assertRedirects(self.client.post(reverse("tournament_results"), data),
                             reverse("tournament_results"))
        result = TournamentResult.objects.get()
        self.assertEqual(result.club, self.club_a)          # ログイン中の部活動の成績になる
        response = self.client.get(reverse("tournament_results"))
        self.assertContains(response, "地区新人大会")
        self.assertContains(response, "優勝")

        self.client.post(reverse("tournament_result_edit", args=[result.pk]), {**data, "achievement": "best8"})
        result.refresh_from_db()
        self.assertEqual(result.achievement, "best8")

        # 他の部活動を指定しても、ログイン中の部活動の成績になる・他の部活動の成績は消せない
        self.client.post(reverse("tournament_results"), {**data, "club": self.club_b.pk})
        self.assertFalse(TournamentResult.objects.filter(club=self.club_b).exists())
        TournamentResult.objects.exclude(pk=result.pk).delete()
        for user in (self.user_b, self.user_a2):
            self.client.force_login(user)
            self.assertEqual(
                self.client.post(reverse("tournament_result_delete", args=[result.pk])).status_code, 404)
            self.assertEqual(list(self.client.get(reverse("tournament_results")).context["results"]), [])

        self.client.force_login(self.user_a)
        self.client.post(reverse("tournament_result_delete", args=[result.pk]))
        self.assertFalse(TournamentResult.objects.exists())

    def test_future_year_is_rejected(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse("tournament_results"), {
            "tournament_name": "大会", "fiscal_year": 2999,
            "level": "district", "achievement": "champion"})
        self.assertContains(response, "開催年度は1990〜")


class RecommendationTest(TestCase):
    """対戦相手検索：競技レベルの推定と、おすすめ順"""

    @classmethod
    def setUpTestData(cls):
        cls.year = current_fiscal_year()
        cls.sport = Sport.objects.create(name="サッカー")

        def club(name, lat):
            school = School.objects.create(
                name=name, code=f"s{lat}".replace(".", "_"), address="北海道", latitude=lat, longitude=141.0)
            return Club.objects.create(school=school, sport=cls.sport, gender="male", code="soccer")

        cls.mine = club("自校", 43.0)
        cls.strong = club("強い高校", 43.5)        # 都道府県大会で優勝
        cls.equal = club("同じくらい高校", 43.2)   # 都道府県大会でベスト8
        cls.weak = club("弱い高校", 43.1)          # 地区大会に出場
        cls.district = club("地区優勝高校", 43.7)          # 地区大会で優勝（自校の都道府県ベスト8より下）
        cls.unknown = club("未登録高校", 43.3)      # 直近の成績なし
        cls.user = User.objects.create_user(username="me", password="x", role="teacher", club=cls.mine)

        def result(c, level, achievement, year=None):
            TournamentResult.objects.create(club=c, tournament_name="大会", fiscal_year=year or cls.year,
                                            level=level, achievement=achievement)

        result(cls.mine, "prefecture", "best8")
        result(cls.mine, "district", "champion")
        result(cls.strong, "prefecture", "champion")
        result(cls.equal, "prefecture", "best8")
        result(cls.weak, "district", "participated")
        result(cls.district, "district", "champion")
        result(cls.unknown, "national", "champion", year=cls.year - 5)   # 古すぎる成績は使わない

    def search(self, level):
        self.client.force_login(self.user)
        response = self.client.get(reverse("opponent_search") + f"?club={self.mine.pk}&level={level}")
        return response, {r["club"].school.name: r for r in response.context["rows"]}

    def test_levels(self):
        _, rows = self.search("same")
        self.assertEqual(rows["強い高校"]["level"]["relation"], "higher")
        self.assertEqual(rows["同じくらい高校"]["level"]["relation"], "same")
        self.assertEqual(rows["弱い高校"]["level"]["relation"], "lower")
        self.assertEqual(rows["未登録高校"]["level"]["relation"], "unknown")
        # 地区大会の成績も、どの学校とも比べる（地区の設定はない）
        self.assertEqual(rows["地区優勝高校"]["level"]["relation"], "lower")

    def test_order_follows_desired_level(self):
        response, _ = self.search("higher")
        names = [r["club"].school.name for r in response.context["rows"]]
        self.assertEqual(len(names), 5)                              # 未登録の学校も含める
        self.assertEqual(names[0], "強い高校")                        # 希望に合う相手が先頭
        self.assertEqual(names[1], "未登録高校")                      # 次に未判定の相手
        self.assertContains(response, "おすすめ")

        response, _ = self.search("lower")
        self.assertEqual(response.context["rows"][0]["club"].school.name, "弱い高校")

    def test_default_level_comes_from_club_setting(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("club_level", args=[self.mine.pk]), {"desired_level": "higher"})
        self.assertRedirects(response, reverse("opponent_search") + f"?club={self.mine.pk}")
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.desired_level, "higher")
        response = self.client.get(reverse("opponent_search") + f"?club={self.mine.pk}")
        self.assertEqual(response.context["selected_level"], "higher")

    def test_head_to_head_is_used(self):
        # 大会成績で比べられない相手でも、過去に2勝していれば「格下」と推定する
        for days in (10, 20):
            match = PracticeMatch.objects.create(
                applicant_club=self.mine, opponent_club=self.unknown, venue_kind="applicant",
                status="confirmed", date=timezone.localdate() - timedelta(days=days))
            MatchResult.objects.create(match=match, applicant_score=3, opponent_score=1)
        _, rows = self.search("same")
        self.assertEqual(rows["未登録高校"]["level"]["relation"], "lower")
        self.assertIn("過去の対戦：2勝0敗", rows["未登録高校"]["level"]["reasons"])

    def test_detail_page(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("opponent_detail", args=[self.mine.pk, self.strong.pk]))
        self.assertContains(response, "強い高校")
        self.assertContains(response, "格上")
        self.assertContains(response, "都道府県大会")
        # 自校の部活動でない組み合わせは開けない
        self.assertEqual(
            self.client.get(reverse("opponent_detail", args=[self.strong.pk, self.mine.pk])).status_code, 404)
