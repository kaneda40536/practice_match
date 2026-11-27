from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View

from accounts.views import AdvisorRequiredMixin, BoardRequiredMixin
from .forms import FacilityForm, SchoolFacilityForm
from .models import Facility


class FacilityListView(BoardRequiredMixin, ListView):
    template_name = "facilities/facility_list.html"
    context_object_name = "facilities"

    def get_queryset(self):
        # 会場として管理するのは公共の施設だけ（学校の会場は登録しない）
        return Facility.objects.filter(school__isnull=True).prefetch_related("sports").order_by("name")


class FacilityCreateView(BoardRequiredMixin, CreateView):
    model = Facility
    form_class = FacilityForm
    template_name = "facilities/facility_form.html"
    success_url = reverse_lazy("facility_list")

    def form_valid(self, form):
        messages.success(self.request, "会場を登録しました。")
        return super().form_valid(form)


class FacilityUpdateView(BoardRequiredMixin, UpdateView):
    queryset = Facility.objects.filter(school__isnull=True)
    form_class = FacilityForm
    template_name = "facilities/facility_form.html"
    success_url = reverse_lazy("facility_list")

    def form_valid(self, form):
        messages.success(self.request, "会場を更新しました。")
        return super().form_valid(form)


class FacilityDeleteView(BoardRequiredMixin, DeleteView):
    queryset = Facility.objects.filter(school__isnull=True)
    template_name = "facilities/facility_confirm_delete.html"
    success_url = reverse_lazy("facility_list")

    def get_context_data(self, **kwargs):
        # 会場として使われている施設は削除できないので、確認画面であらかじめ知らせる
        context = super().get_context_data(**kwargs)
        context["match_count"] = self.object.practicematch_set.count()
        return context

    def form_valid(self, form):
        name = self.object.name
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "この会場は、練習試合の会場として使われているため、削除できません。")
            return redirect("facility_list")
        messages.success(self.request, f"「{name}」を削除しました。")
        return response


# ---------- 会場管理（顧問：学校内の施設） ----------

def school_facilities(school):
    return Facility.objects.filter(school=school).prefetch_related("sports").order_by("name")


class SchoolFacilityListView(AdvisorRequiredMixin, View):
    """自校の施設の一覧と、登録フォーム"""
    template_name = "facilities/school_facility_list.html"

    def show(self, form):
        return render(self.request, self.template_name, {
            "form": form,
            "facilities": school_facilities(self.request.user.school),
        })

    def get(self, request):
        return self.show(SchoolFacilityForm(school=request.user.school))

    def post(self, request):
        form = SchoolFacilityForm(request.POST, school=request.user.school)
        if not form.is_valid():
            return self.show(form)
        facility = form.save()
        messages.success(request, f"会場「{facility.name}」を登録しました。")
        return redirect("my_facility_list")


class SchoolFacilityUpdateView(AdvisorRequiredMixin, View):
    template_name = "facilities/school_facility_form.html"

    def get_facility(self):
        return get_object_or_404(Facility, pk=self.kwargs["pk"], school=self.request.user.school)

    def show(self, form, facility):
        return render(self.request, self.template_name, {"form": form, "facility": facility})

    def get(self, request, pk):
        facility = self.get_facility()
        return self.show(SchoolFacilityForm(instance=facility, school=request.user.school), facility)

    def post(self, request, pk):
        facility = self.get_facility()
        form = SchoolFacilityForm(request.POST, instance=facility, school=request.user.school)
        if not form.is_valid():
            return self.show(form, facility)
        form.save()
        messages.success(request, f"会場「{facility.name}」を変更しました。")
        return redirect("my_facility_list")


class SchoolFacilityDeleteView(AdvisorRequiredMixin, View):
    """自校の施設を削除する（一覧の削除ボタンから。練習試合の会場になっていれば削除できない）"""

    def post(self, request, pk):
        facility = get_object_or_404(Facility, pk=pk, school=request.user.school)
        name = facility.name
        try:
            facility.delete()
        except ProtectedError:
            messages.error(request, f"会場「{name}」は、練習試合の会場になっているため削除できません。")
        else:
            messages.success(request, f"会場「{name}」を削除しました。")
        return redirect("my_facility_list")
