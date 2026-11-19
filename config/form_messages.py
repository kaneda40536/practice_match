from django import forms

# Django がもともと持っている「必須です」のメッセージ（これだけを置き換える）
DEFAULT_REQUIRED = str(forms.Field.default_error_messages["required"])


class RequiredMessageMixin:
    """未入力のときのエラーを「○○を入力してください。」「○○を選択してください。」にする部品

    画面のフォームには novalidate を付けてブラウザのチェックを止めているので、
    未入力のエラーはサーバー側のこのメッセージで表示される。
    フォームのクラスで個別にメッセージを決めている項目は、そのまま使う。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if str(field.error_messages.get("required", "")) != DEFAULT_REQUIRED:
                continue
            label = field.label or name
            verb = "選択" if isinstance(field, forms.ChoiceField) else "入力"
            field.error_messages["required"] = f"{label}を{verb}してください。"
