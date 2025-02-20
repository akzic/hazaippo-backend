# app/forms.py

from flask_wtf import FlaskForm
from wtforms import (
    SelectMultipleField, StringField, PasswordField, SubmitField, BooleanField,
    IntegerField, DateTimeField, SelectField, FileField, DateField, DecimalField,
    TextAreaField, FloatField, FieldList, FormField, DateTimeLocalField, RadioField
)
from wtforms.validators import (
    DataRequired, Length, Email, EqualTo, NumberRange, Optional, Regexp, ValidationError
)
from flask_login import current_user
from app.models import User
from datetime import datetime
import pytz
import logging

JST = pytz.timezone('Asia/Tokyo')

# ログ設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class RegistrationForm(FlaskForm):
    business_structure = SelectField(
        '登録形態',
        choices=[
            ('', '選択してください'),
            ('0', '法人'),
            ('1', '個人事業主'),
            ('2', '個人')
        ],
        validators=[DataRequired(message="登録形態を選択してください。")]
    )

    company_name = StringField(
        '法人名/屋号/ニックネーム',
        validators=[DataRequired(message="このフィールドは必須です。")]
    )

    company_phone = StringField(
        '電話番号',
        validators=[Optional(), Length(min=10, max=20, message="電話番号は10〜20桁で入力してください。")]
    )

    prefecture = SelectField(
        '住所',
        choices=[
            ('', '選択してください'),
            # 以下、都道府県の選択肢
            ('北海道', '北海道'),
            ('青森県', '青森県'),
            ('岩手県', '岩手県'),
            ('宮城県', '宮城県'),
            ('秋田県', '秋田県'),
            ('山形県', '山形県'),
            ('福島県', '福島県'),
            ('茨城県', '茨城県'),
            ('栃木県', '栃木県'),
            ('群馬県', '群馬県'),
            ('埼玉県', '埼玉県'),
            ('千葉県', '千葉県'),
            ('東京都', '東京都'),
            ('神奈川県', '神奈川県'),
            ('新潟県', '新潟県'),
            ('富山県', '富山県'),
            ('石川県', '石川県'),
            ('福井県', '福井県'),
            ('山梨県', '山梨県'),
            ('長野県', '長野県'),
            ('岐阜県', '岐阜県'),
            ('静岡県', '静岡県'),
            ('愛知県', '愛知県'),
            ('三重県', '三重県'),
            ('滋賀県', '滋賀県'),
            ('京都府', '京都府'),
            ('大阪府', '大阪府'),
            ('兵庫県', '兵庫県'),
            ('奈良県', '奈良県'),
            ('和歌山県', '和歌山県'),
            ('鳥取県', '鳥取県'),
            ('島根県', '島根県'),
            ('岡山県', '岡山県'),
            ('広島県', '広島県'),
            ('山口県', '山口県'),
            ('徳島県', '徳島県'),
            ('香川県', '香川県'),
            ('愛媛県', '愛媛県'),
            ('高知県', '高知県'),
            ('福岡県', '福岡県'),
            ('佐賀県', '佐賀県'),
            ('長崎県', '長崎県'),
            ('熊本県', '熊本県'),
            ('大分県', '大分県'),
            ('宮崎県', '宮崎県'),
            ('鹿児島県', '鹿児島県'),
            ('沖縄県', '沖縄県')
        ],
        validators=[DataRequired(message="都道府県を選択してください。")]
    )

    city = StringField(
        '市区町村',
        validators=[DataRequired(message="市区町村を入力してください。")]
    )
    address = StringField(
        'それ以降の住所',
        validators=[DataRequired(message="住所を入力してください。")]
    )

    contact_phone = StringField(
        '担当者電話番号',
        validators=[Optional(), Length(min=10, max=20, message="電話番号は10〜20桁で入力してください。")]
    )

    individual_phone = StringField(
        '電話番号',
        validators=[Optional(), Length(min=10, max=20, message="電話番号は10〜20桁で入力してください。")]
    )

    industry = SelectField(
        '業種',
        choices=[
            ('ゼネコン', 'ゼネコン'),
            ('工務店', '工務店'),
            ('木工業', '木工業'),
            ('リフォーム業', 'リフォーム業'),
            ('内装工事業', '内装工事業'),
            ('ハウスメーカー', 'ハウスメーカー'),
            ('専門職業(一人親方)', '専門職業(一人親方)'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )

    job_title = SelectField(
        '職種',
        choices=[
            ('木工大工', '木工大工'),
            ('ボード施工', 'ボード施工'),
            ('床施工', '床施工'),
            ('軽量鉄骨施工', '軽量鉄骨施工'),
            ('電気設備', '電気設備'),
            ('衛生設備', '衛生設備'),
            ('クロス施工', 'クロス施工'),
            ('左官', '左官'),
            ('塗装', '塗装'),
            ('屋根施工', '屋根施工'),
            ('外壁施工', '外壁施工'),
            ('解体', '解体'),
            ('外構施工', '外構施工'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )

    without_approval = BooleanField('リクエスト受け取り時、承認をスキップする')

    contact_name = StringField(
        '担当者名',
        validators=[DataRequired(message="担当者名を入力してください。")]
    )
    contact_email = StringField(
        'メールアドレス',
        validators=[
            DataRequired(message="メールアドレスを入力してください。"),
            Email(message="有効なメールアドレスを入力してください。")
        ]
    )

    password = PasswordField(
        'パスワード',
        validators=[
            DataRequired(message="パスワードを入力してください。"),
            Length(min=6, max=32, message="パスワードは6〜32文字で入力してください。")
        ]
    )
    confirm_password = PasswordField(
        'パスワード確認',
        validators=[
            DataRequired(message="パスワード確認を入力してください。"),
            EqualTo('password', message="パスワードが一致しません。")
        ]
    )

    terms = BooleanField(
        '利用規約に同意します',
        validators=[DataRequired(message="利用規約に同意してください。")]
    )
    privacy = BooleanField(
        'プライバシーポリシーに同意します',
        validators=[DataRequired(message="プライバシーポリシーに同意してください。")]
    )

    submit = SubmitField('登録')

    def validate_industry(self, field):
        if self.business_structure.data not in ['2'] and not field.data:
            raise ValidationError("業種を選択してください。")

    def validate_job_title(self, field):
        if self.business_structure.data not in ['2'] and not field.data:
            raise ValidationError("職種を選択してください。")

    def validate_company_phone(self, field):
        if self.business_structure.data in ['0', '1'] and not field.data:
            raise ValidationError("法人電話番号を入力してください。")

    def validate_individual_phone(self, field):
        if self.business_structure.data == '2' and not field.data:
            raise ValidationError("電話番号を入力してください。")

    def validate_contact_phone(self, field):
        if self.business_structure.data in ['0', '1'] and not field.data:
            raise ValidationError("担当者電話番号を入力してください。")
        
class LoginForm(FlaskForm):
    email = StringField(
        'Email',
        validators=[DataRequired(message="メールアドレスを入力してください。"), Email(message="有効なメールアドレスを入力してください。")],
        render_kw={"autocomplete": "email"}
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired(message="パスワードを入力してください。")],
        render_kw={"autocomplete": "current-password"}
    )
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class RequestResetForm(FlaskForm):
    email = StringField(
        'Email',
        validators=[DataRequired(message="メールアドレスを入力してください。"), Email(message="有効なメールアドレスを入力してください。")],
        render_kw={"autocomplete": "email"}
    )
    submit = SubmitField('Request Password Reset')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is None:
            raise ValidationError('このメールアドレスに該当するアカウントはありません。')

class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        'Password',
        validators=[DataRequired(message="パスワードを入力してください。"), Length(min=6, max=20, message="パスワードは6～20文字で入力してください。")],
        render_kw={"autocomplete": "new-password"}
    )
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(message="パスワード確認を入力してください。"), EqualTo('password', message="パスワードが一致しません。")],
        render_kw={"autocomplete": "new-password"}
    )
    submit = SubmitField('Reset Password')

class TimeSlotForm(FlaskForm):
    time_slot = StringField('稼働時間', validators=[DataRequired(message="稼働時間を入力してください。")])
    is_checked = BooleanField('稼働可能チェック', default=False)

class WorkingHoursForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired(message="日付を選択してください。")])
    time_slots = FieldList(
        FormField(TimeSlotForm),
        min_entries=1  # 複数の時間スロットを処理
    )
    submit = SubmitField('予定を送信する')

class MaterialForm(FlaskForm):
    # 受け渡しオプションの選択（オプションに変更）
    delivery_option = RadioField(
        '受け渡し場所の選択',
        choices=[
            ('select', '選択'),
            ('free', '自由入力')
        ],
        default='select',
        validators=[Optional()]
    )
    
    material_type = SelectField(
        '端材の種類',
        id='material_type',
        choices=[
            ('', '選択してください'),
            ('木材', '木材'),
            ('軽量鉄骨', '軽量鉄骨'),
            ('ボード材', 'ボード材'),
            ('パネル材', 'パネル材'),
            ('その他', 'その他')
        ],
        validators=[DataRequired(message="端材の種類を選択してください。")]
    )
    
    # サブタイプフィールドをオプションに変更
    wood_type = SelectField(
        '木材の種類',
        id='wood_type',
        choices=[
            ('', '選択してください'),
            ('無垢材', '無垢材'),
            ('集成材（積層材）', '集成材（積層材）'),
            ('広葉樹', '広葉樹'),
            ('針葉樹', '針葉樹'),
            ('ヒノキ', 'ヒノキ'),
            ('スギ', 'スギ'),
            ('ヒバ', 'ヒバ'),
            ('マツ（ベイマツ、アカマツ）', 'マツ（ベイマツ、アカマツ）'),
            ('ケヤキ', 'ケヤキ'),
            ('ツガ', 'ツガ'),
            ('キリ', 'キリ'),
            ('ホワイトウッド', 'ホワイトウッド'),
            ('ウォールナット', 'ウォールナット'),
            ('パイン', 'パイン'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    board_material_type = SelectField(
        'ボード材の種類',
        id='board_material_type',
        choices=[
            ('', '選択してください'),
            ('プラスターボード', 'プラスターボード'),
            ('強化ボード', '強化ボード'),
            ('耐火ボード', '耐火ボード'),
            ('耐水(防水)ボード', '耐水(防水)ボード'),
            ('岩綿吸音板', '岩綿吸音板'),
            ('圭カル板', '圭カル板'),
            ('化粧石膏ボード', '化粧石膏ボード'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    panel_type = SelectField(
        'パネル材の種類',
        id='panel_type',
        choices=[
            ('', '選択してください'),
            ('キッチンパネル', 'キッチンパネル'),
            ('化粧板', '化粧板'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    material_size_1 = FloatField(
        'サイズ1（mm）',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    material_size_2 = FloatField(
        'サイズ2（mm）',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    material_size_3 = FloatField(
        'サイズ3（mm）',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    
    # 受け渡し場所を分割して入力
    m_prefecture = SelectField(
        '都道府県',
        choices=[
            ('', '選択してください'),
            ('北海道', '北海道'),
            ('青森県', '青森県'),
            ('岩手県', '岩手県'),
            ('宮城県', '宮城県'),
            ('秋田県', '秋田県'),
            ('山形県', '山形県'),
            ('福島県', '福島県'),
            ('茨城県', '茨城県'),
            ('栃木県', '栃木県'),
            ('群馬県', '群馬県'),
            ('埼玉県', '埼玉県'),
            ('千葉県', '千葉県'),
            ('東京都', '東京都'),
            ('神奈川県', '神奈川県'),
            ('新潟県', '新潟県'),
            ('富山県', '富山県'),
            ('石川県', '石川県'),
            ('福井県', '福井県'),
            ('山梨県', '山梨県'),
            ('長野県', '長野県'),
            ('岐阜県', '岐阜県'),
            ('静岡県', '静岡県'),
            ('愛知県', '愛知県'),
            ('三重県', '三重県'),
            ('滋賀県', '滋賀県'),
            ('京都府', '京都府'),
            ('大阪府', '大阪府'),
            ('兵庫県', '兵庫県'),
            ('奈良県', '奈良県'),
            ('和歌山県', '和歌山県'),
            ('鳥取県', '鳥取県'),
            ('島根県', '島根県'),
            ('岡山県', '岡山県'),
            ('広島県', '広島県'),
            ('山口県', '山口県'),
            ('徳島県', '徳島県'),
            ('香川県', '香川県'),
            ('愛媛県', '愛媛県'),
            ('高知県', '高知県'),
            ('福岡県', '福岡県'),
            ('佐賀県', '佐賀県'),
            ('長崎県', '長崎県'),
            ('熊本県', '熊本県'),
            ('大分県', '大分県'),
            ('宮崎県', '宮崎県'),
            ('鹿児島県', '鹿児島県'),
            ('沖縄県', '沖縄県')
        ],
        validators=[DataRequired(message="受け渡しの都道府県を入力してください。")]
    )
    m_city = StringField(
        '市区町村',
        validators=[Optional()],
        render_kw={"autocomplete": "off", "list": "city_options"}
    )
    m_address = StringField(
        '住所',
        validators=[Optional()],
        render_kw={"autocomplete": "off", "list": "address_options"}
    )
    
    # datalistのためのID
    city_datalist_id = 'city_options'
    address_datalist_id = 'address_options'
    
    quantity = IntegerField(
        '数量',
        validators=[DataRequired(message="数量を入力してください。")],
        render_kw={"autocomplete": "off"}
    )

    deadline = DateTimeField(
        '締め切り日時',
        format='%Y-%m-%dT%H:%M',
        validators=[DataRequired(message="締め切り日時を入力してください。")],
        render_kw={"autocomplete": "off"}
    )
    exclude_weekends = BooleanField('土日を除く')  # 新しいチェックボックス
    image = FileField('画像', validators=[Optional()])
    note = TextAreaField('受け渡し時の注意点', validators=[Optional()])
    
    submit = SubmitField('登録')
    
    def validate_deadline(self, deadline):
        logger.debug("締め切り日時のバリデーションを開始します。")
        if deadline.data is None:
            logger.debug("締め切り日時が入力されていません。")
            raise ValidationError('締め切り日時を入力してください。')

        # deadline.data を JST タイムゾーンでローカライズ
        JST = pytz.timezone('Asia/Tokyo')
        if deadline.data.tzinfo is None:
            try:
                deadline_aware = JST.localize(deadline.data)
                logger.debug(f"ローカライズされた締め切り日時: {deadline_aware}")
            except Exception as e:
                logger.error(f"タイムゾーンローカライズエラー: {e}")
                raise ValidationError('締め切り日時のタイムゾーン処理でエラーが発生しました。')
        else:
            deadline_aware = deadline.data.astimezone(JST)
            logger.debug(f"JSTに変換された締め切り日時: {deadline_aware}")

        current_time = datetime.now(JST)
        logger.debug(f"現在のJST時刻: {current_time}")

        if deadline_aware < current_time:
            logger.debug("締め切り日時が現在時刻より前です。")
            raise ValidationError('締め切り日時は登録日時以降にしてください。')
        logger.debug("締め切り日時のバリデーションに成功しました。")
    
    def validate(self, *args, **kwargs):
        rv = super().validate(*args, **kwargs)
        if not rv:
            logger.debug("フォームのバリデーションに失敗しました。エラー内容をログに記録します。")
            for fieldName, errorMessages in self.errors.items():
                for err in errorMessages:
                    logger.debug(f"バリデーションエラー - フィールド: {fieldName}, エラー: {err}")
            return False

        # サブタイプフィールドのバリデーションを削除
        # 以前のサブタイプフィールドのバリデーションロジックを削除しました

        logger.debug("フォームのバリデーションに成功しました。")
        return True


class MaterialSearchForm(FlaskForm):
    material_type = SelectField(
        '端材の種類',
        id='search_material_type',
        choices=[
            ('', '選択してください'),
            ('木材', '木材'),
            ('軽量鉄骨', '軽量鉄骨'),
            ('ボード材', 'ボード材'),
            ('パネル材', 'パネル材'),
            ('その他', 'その他')
        ],
        validators=[DataRequired(message="端材の種類を選択してください。")]
    )
    
    # 木材の種類フィールド
    wood_type = SelectField(
        '木材の種類',
        id='wood_type',
        choices=[
            ('', '選択してください'),
            ('無垢材', '無垢材'),
            ('集成材（積層材）', '集成材（積層材）'),
            ('広葉樹', '広葉樹'),
            ('針葉樹', '針葉樹'),
            ('ヒノキ', 'ヒノキ'),
            ('スギ', 'スギ'),
            ('ヒバ', 'ヒバ'),
            ('マツ（ベイマツ、アカマツ）', 'マツ（ベイマツ、アカマツ）'),
            ('ケヤキ', 'ケヤキ'),
            ('ツガ', 'ツガ'),
            ('キリ', 'キリ'),
            ('ホワイトウッド', 'ホワイトウッド'),
            ('ウォールナット', 'ウォールナット'),
            ('パイン', 'パイン'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    # ボード材の種類フィールド
    board_material_type = SelectField(
        'ボード材の種類',
        id='board_material_type',
        choices=[
            ('', '選択してください'),
            ('プラスターボード', 'プラスターボード'),
            ('強化ボード', '強化ボード'),
            ('耐火ボード', '耐火ボード'),
            ('耐水(防水)ボード', '耐水(防水)ボード'),
            ('岩綿吸音板', '岩綿吸音板'),
            ('圭カル板', '圭カル板'),
            ('化粧石膏ボード', '化粧石膏ボード'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    # パネル材の種類フィールド
    panel_type = SelectField(
        'パネル材の種類',
        id='panel_type',
        choices=[
            ('', '選択してください'),
            ('キッチンパネル', 'キッチンパネル'),
            ('化粧板', '化粧板'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    # サイズフィールド
    material_size_1 = DecimalField(
        'サイズ1（mm）',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    material_size_2 = DecimalField(
        'サイズ2（mm）',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    material_size_3 = DecimalField(
        'サイズ3（mm）',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    
    # 都道府県フィールド
    m_prefecture = SelectField(
        '都道府県',
        choices=[
            ('', '選択してください'),
            ('北海道', '北海道'),
            ('青森県', '青森県'),
            ('岩手県', '岩手県'),
            ('宮城県', '宮城県'),
            ('秋田県', '秋田県'),
            ('山形県', '山形県'),
            ('福島県', '福島県'),
            ('茨城県', '茨城県'),
            ('栃木県', '栃木県'),
            ('群馬県', '群馬県'),
            ('埼玉県', '埼玉県'),
            ('千葉県', '千葉県'),
            ('東京都', '東京都'),
            ('神奈川県', '神奈川県'),
            ('新潟県', '新潟県'),
            ('富山県', '富山県'),
            ('石川県', '石川県'),
            ('福井県', '福井県'),
            ('山梨県', '山梨県'),
            ('長野県', '長野県'),
            ('岐阜県', '岐阜県'),
            ('静岡県', '静岡県'),
            ('愛知県', '愛知県'),
            ('三重県', '三重県'),
            ('滋賀県', '滋賀県'),
            ('京都府', '京都府'),
            ('大阪府', '大阪府'),
            ('兵庫県', '兵庫県'),
            ('奈良県', '奈良県'),
            ('和歌山県', '和歌山県'),
            ('鳥取県', '鳥取県'),
            ('島根県', '島根県'),
            ('岡山県', '岡山県'),
            ('広島県', '広島県'),
            ('山口県', '山口県'),
            ('徳島県', '徳島県'),
            ('香川県', '香川県'),
            ('愛媛県', '愛媛県'),
            ('高知県', '高知県'),
            ('福岡県', '福岡県'),
            ('佐賀県', '佐賀県'),
            ('長崎県', '長崎県'),
            ('熊本県', '熊本県'),
            ('大分県', '大分県'),
            ('宮崎県', '宮崎県'),
            ('鹿児島県', '鹿児島県'),
            ('沖縄県', '沖縄県')
        ],
        validators=[DataRequired(message="受け渡しの都道府県を入力してください。")]
    )
    
    # 市区町村フィールド
    m_city = StringField(
        '市区町村',
        validators=[Optional()],
        render_kw={"placeholder": "市区町村を入力してください", "autocomplete": "off"}
    )
    
    submit = SubmitField('検索')
    
    def validate(self, *args, **kwargs):
        rv = super().validate(*args, **kwargs)
        if not rv:
            logger.debug("フォームのバリデーションに失敗しました。エラー内容をログに記録します。")
            for fieldName, errorMessages in self.errors.items():
                for err in errorMessages:
                    logger.debug(f"バリデーションエラー - フィールド: {fieldName}, エラー: {err}")
            return False

        # サブタイプフィールドのバリデーション
        if self.material_type.data == '木材' and not self.wood_type.data:
            self.wood_type.errors.append("木材の種類を選択してください。")
            return False
        elif self.material_type.data == 'ボード材' and not self.board_material_type.data:
            self.board_material_type.errors.append("ボード材の種類を選択してください。")
            return False
        elif self.material_type.data == 'パネル材' and not self.panel_type.data:
            self.panel_type.errors.append("パネル材の種類を選択してください。")
            return False

        logger.debug("フォームのバリデーションに成功しました。")
        return True

class WantedMaterialForm(FlaskForm):
    material_type = SelectField(
        '材料の種類',
        id='wanted_material_type',
        choices=[
            ('', '選択してください'),
            ('木材', '木材'),
            ('軽量鉄骨', '軽量鉄骨'),
            ('ボード材', 'ボード材'),
            ('パネル材', 'パネル材'),
            ('その他', 'その他')
        ],
        validators=[DataRequired(message="材料の種類を選択してください。")]
    )
    
    # サブタイプフィールド
    wood_type = SelectField(
        '木材の種類',
        id='wanted_wood_type',
        choices=[
            ('', '選択してください'),
            ('無垢材', '無垢材'),
            ('集成材（積層材）', '集成材（積層材）'),
            ('広葉樹', '広葉樹'),
            ('針葉樹', '針葉樹'),
            ('ヒノキ', 'ヒノキ'),
            ('スギ', 'スギ'),
            ('ヒバ', 'ヒバ'),
            ('マツ（ベイマツ、アカマツ）', 'マツ（ベイマツ、アカマツ）'),
            ('ケヤキ', 'ケヤキ'),
            ('ツガ', 'ツガ'),
            ('キリ', 'キリ'),
            ('ホワイトウッド', 'ホワイトウッド'),
            ('ウォールナット', 'ウォールナット'),
            ('パイン', 'パイン'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    board_material_type = SelectField(
        'ボード材の種類',
        id='wanted_board_material_type',
        choices=[
            ('', '選択してください'),
            ('プラスターボード', 'プラスターボード'),
            ('強化ボード', '強化ボード'),
            ('耐火ボード', '耐火ボード'),
            ('耐水(防水)ボード', '耐水(防水)ボード'),
            ('岩綿吸音板', '岩綿吸音板'),
            ('圭カル板', '圭カル板'),
            ('化粧石膏ボード', '化粧石膏ボード'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    panel_type = SelectField(
        'パネル材の種類',
        id='wanted_panel_type',
        choices=[
            ('', '選択してください'),
            ('キッチンパネル', 'キッチンパネル'),
            ('化粧板', '化粧板'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    material_size_1 = FloatField(
        'サイズ1（mm）',
        validators=[
            Optional(),
            NumberRange(min=0.1, message="サイズ1には0より大きい値を入力してください。")
        ],
        render_kw={"autocomplete": "off"}
    )
    material_size_2 = FloatField(
        'サイズ2（mm）',
        validators=[
            Optional(),
            NumberRange(min=0.1, message="サイズ2には0より大きい値を入力してください。")
        ],
        render_kw={"autocomplete": "off"}
    )
    material_size_3 = FloatField(
        'サイズ3（mm）',
        validators=[
            Optional(),
            NumberRange(min=0.1, message="サイズ3には0より大きい値を入力してください。")
        ],
        render_kw={"autocomplete": "off"}
    )
    
    location = SelectField(
        '場所',
        choices=[
            ('', '選択してください'),
            ('北海道', '北海道'),
            ('青森県', '青森県'),
            ('岩手県', '岩手県'),
            ('宮城県', '宮城県'),
            ('秋田県', '秋田県'),
            ('山形県', '山形県'),
            ('福島県', '福島県'),
            ('茨城県', '茨城県'),
            ('栃木県', '栃木県'),
            ('群馬県', '群馬県'),
            ('埼玉県', '埼玉県'),
            ('千葉県', '千葉県'),
            ('東京都', '東京都'),
            ('神奈川県', '神奈川県'),
            ('新潟県', '新潟県'),
            ('富山県', '富山県'),
            ('石川県', '石川県'),
            ('福井県', '福井県'),
            ('山梨県', '山梨県'),
            ('長野県', '長野県'),
            ('岐阜県', '岐阜県'),
            ('静岡県', '静岡県'),
            ('愛知県', '愛知県'),
            ('三重県', '三重県'),
            ('滋賀県', '滋賀県'),
            ('京都府', '京都府'),
            ('大阪府', '大阪府'),
            ('兵庫県', '兵庫県'),
            ('奈良県', '奈良県'),
            ('和歌山県', '和歌山県'),
            ('鳥取県', '鳥取県'),
            ('島根県', '島根県'),
            ('岡山県', '岡山県'),
            ('広島県', '広島県'),
            ('山口県', '山口県'),
            ('徳島県', '徳島県'),
            ('香川県', '香川県'),
            ('愛媛県', '愛媛県'),
            ('高知県', '高知県'),
            ('福岡県', '福岡県'),
            ('佐賀県', '佐賀県'),
            ('長崎県', '長崎県'),
            ('熊本県', '熊本県'),
            ('大分県', '大分県'),
            ('宮崎県', '宮崎県'),
            ('鹿児島県', '鹿児島県'),
            ('沖縄県', '沖縄県')
        ],
        validators=[Optional()]  # 必須ではなくオプションに変更
    )
    
    quantity = IntegerField('数量', validators=[
        DataRequired(message="数量を入力してください。"),
        NumberRange(min=1, max=100, message="数量は1から100までの値を入力してください。")
    ])
    deadline = DateTimeLocalField(
        '締め切り',
        format='%Y-%m-%dT%H:%M',
        validators=[Optional()]
    )
    note = TextAreaField('備考', validators=[Optional()])
    
    exclude_weekends = BooleanField(
        '週末を除外する',
        validators=[Optional()]
    )
    
    submit = SubmitField('登録')
    
    def validate_deadline(self, deadline):
        logger.debug("締め切り日時のバリデーションを開始します。")
        if deadline.data is None:
            logger.debug("締め切り日時が入力されていません。")
            raise ValidationError('締め切り日時を入力してください。')

        # deadline.data を JST タイムゾーンでローカライズ
        if deadline.data.tzinfo is None:
            try:
                # JST.localize(deadline.data)  # タイムゾーン設定が必要な場合
                deadline_aware = deadline.data  # 仮にタイムゾーンなしとして扱う
                logger.debug(f"ローカライズされた締め切り日時: {deadline_aware}")
            except Exception as e:
                logger.error(f"タイムゾーンローカライズエラー: {e}")
                raise ValidationError('締め切り日時のタイムゾーン処理でエラーが発生しました。')
        else:
            # deadline_aware = deadline.data.astimezone(JST)  # タイムゾーン設定が必要な場合
            deadline_aware = deadline.data  # 仮にタイムゾーンありとして扱う
            logger.debug(f"JSTに変換された締め切り日時: {deadline_aware}")

        current_time = datetime.now()  # JSTの場合は datetime.now(JST) に変更
        logger.debug(f"現在の時刻: {current_time}")

        if deadline_aware < current_time:
            logger.debug("締め切り日時が現在時刻より前です。")
            raise ValidationError('締め切り日時は登録日時以降にしてください。')
        logger.debug("締め切り日時のバリデーションに成功しました。")
    
    def validate(self, *args, **kwargs):
        rv = super().validate(*args, **kwargs)
        if not rv:
            logger.debug("フォームのバリデーションに失敗しました。エラー内容をログに記録します。")
            for fieldName, errorMessages in self.errors.items():
                for err in errorMessages:
                    logger.debug(f"バリデーションエラー - フィールド: {fieldName}, エラー: {err}")
            return False

        # material_type に基づくサブタイプフィールドのバリデーション
        if self.material_type.data == '木材' and not self.wood_type.data:
            self.wood_type.errors.append("木材の種類を選択してください。")
            return False
        elif self.material_type.data == 'パネル材' and not self.panel_type.data:
            self.panel_type.errors.append("パネル材の種類を選択してください。")
            return False
        elif self.material_type.data == 'ボード材' and not self.board_material_type.data:
            self.board_material_type.errors.append("ボード材の種類を選択してください。")
            return False
        # 以下の部分を削除またはコメントアウト
        # elif self.material_type.data == '軽量鉄骨' and not self.handover_location.data:
        #     # handover_location が不要な場合、以下を削除
        #     pass

        logger.debug("フォームのバリデーションに成功しました。")
        return True


class WantedMaterialSearchForm(FlaskForm):
    material_type = SelectField(
        '材料の種類',
        id='material_type',
        choices=[
            ('', '選択してください'),
            ('木材', '木材'),
            ('軽量鉄骨', '軽量鉄骨'),
            ('ボード材', 'ボード材'),
            ('パネル材', 'パネル材'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    # サブタイプフィールド（オプショナルに変更）
    wood_type = SelectField(
        '木材の種類',
        id='wood_type_wanted',
        choices=[
            ('', '選択してください'),
            ('無垢材', '無垢材'),
            ('集成材（積層材）', '集成材（積層材）'),
            ('広葉樹', '広葉樹'),
            ('針葉樹', '針葉樹'),
            ('ヒノキ', 'ヒノキ'),
            ('スギ', 'スギ'),
            ('ヒバ', 'ヒバ'),
            ('マツ（ベイマツ、アカマツ）', 'マツ（ベイマツ、アカマツ）'),
            ('ケヤキ', 'ケヤキ'),
            ('ツガ', 'ツガ'),
            ('キリ', 'キリ'),
            ('ホワイトウッド', 'ホワイトウッド'),
            ('ウォールナット', 'ウォールナット'),
            ('パイン', 'パイン'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    board_material_type = SelectField(
        'ボード材の種類',
        id='board_material_type_wanted',
        choices=[
            ('', '選択してください'),
            ('プラスターボード', 'プラスターボード'),
            ('強化ボード', '強化ボード'),
            ('耐火ボード', '耐火ボード'),
            ('耐水(防水)ボード', '耐水(防水)ボード'),
            ('岩綿吸音板', '岩綿吸音板'),
            ('圭カル板', '圭カル板'),
            ('化粧石膏ボード', '化粧石膏ボード'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    panel_type = SelectField(
        'パネル材の種類',
        id='panel_type_wanted',
        choices=[
            ('', '選択してください'),
            ('キッチンパネル', 'キッチンパネル'),
            ('化粧板', '化粧板'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    material_size_1 = FloatField(
        'サイズ1（mm）',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    material_size_2 = FloatField(
        'サイズ2（mm）',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    material_size_3 = FloatField(
        'サイズ3（mm）',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    
    location = SelectField(
        '場所',
        id='location',
        choices=[
            ('', '選択してください'),
            ('北海道', '北海道'),
            ('青森県', '青森県'),
            ('岩手県', '岩手県'),
            ('宮城県', '宮城県'),
            ('秋田県', '秋田県'),
            ('山形県', '山形県'),
            ('福島県', '福島県'),
            ('茨城県', '茨城県'),
            ('栃木県', '栃木県'),
            ('群馬県', '群馬県'),
            ('埼玉県', '埼玉県'),
            ('千葉県', '千葉県'),
            ('東京都', '東京都'),
            ('神奈川県', '神奈川県'),
            ('新潟県', '新潟県'),
            ('富山県', '富山県'),
            ('石川県', '石川県'),
            ('福井県', '福井県'),
            ('山梨県', '山梨県'),
            ('長野県', '長野県'),
            ('岐阜県', '岐阜県'),
            ('静岡県', '静岡県'),
            ('愛知県', '愛知県'),
            ('三重県', '三重県'),
            ('滋賀県', '滋賀県'),
            ('京都府', '京都府'),
            ('大阪府', '大阪府'),
            ('兵庫県', '兵庫県'),
            ('奈良県', '奈良県'),
            ('和歌山県', '和歌山県'),
            ('鳥取県', '鳥取県'),
            ('島根県', '島根県'),
            ('岡山県', '岡山県'),
            ('広島県', '広島県'),
            ('山口県', '山口県'),
            ('徳島県', '徳島県'),
            ('香川県', '香川県'),
            ('愛媛県', '愛媛県'),
            ('高知県', '高知県'),
            ('福岡県', '福岡県'),
            ('佐賀県', '佐賀県'),
            ('長崎県', '長崎県'),
            ('熊本県', '熊本県'),
            ('大分県', '大分県'),
            ('宮崎県', '宮崎県'),
            ('鹿児島県', '鹿児島県'),
            ('沖縄県', '沖縄県')
        ],
        validators=[Optional()]
    )
    
    m_city = StringField(
        '市区町村',
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )
    
    # **Added Fields**
    quantity = IntegerField('数量', validators=[Optional()])
    deadline = DateTimeLocalField(
        '締め切り',
        format='%Y-%m-%dT%H:%M',
        validators=[Optional()]
    )
    exclude_weekends = BooleanField(
        '週末を除外する',
        validators=[Optional()]
    )
    note = TextAreaField('備考', validators=[Optional()])
    
    submit = SubmitField('検索')



class EditProfileForm(FlaskForm):
    company_name = StringField(
        '法人名（屋号）',
        validators=[DataRequired(message="法人名を入力してください。")],
        render_kw={"autocomplete": "organization", "readonly": True}
    )
    
    prefecture = SelectField(
        '県',
        choices=[
            ('', '選択してください'),
            ('北海道', '北海道'),
            ('青森県', '青森県'),
            ('岩手県', '岩手県'),
            ('宮城県', '宮城県'),
            ('秋田県', '秋田県'),
            ('山形県', '山形県'),
            ('福島県', '福島県'),
            ('茨城県', '茨城県'),
            ('栃木県', '栃木県'),
            ('群馬県', '群馬県'),
            ('埼玉県', '埼玉県'),
            ('千葉県', '千葉県'),
            ('東京都', '東京都'),
            ('神奈川県', '神奈川県'),
            ('新潟県', '新潟県'),
            ('富山県', '富山県'),
            ('石川県', '石川県'),
            ('福井県', '福井県'),
            ('山梨県', '山梨県'),
            ('長野県', '長野県'),
            ('岐阜県', '岐阜県'),
            ('静岡県', '静岡県'),
            ('愛知県', '愛知県'),
            ('三重県', '三重県'),
            ('滋賀県', '滋賀県'),
            ('京都府', '京都府'),
            ('大阪府', '大阪府'),
            ('兵庫県', '兵庫県'),
            ('奈良県', '奈良県'),
            ('和歌山県', '和歌山県'),
            ('鳥取県', '鳥取県'),
            ('島根県', '島根県'),
            ('岡山県', '岡山県'),
            ('広島県', '広島県'),
            ('山口県', '山口県'),
            ('徳島県', '徳島県'),
            ('香川県', '香川県'),
            ('愛媛県', '愛媛県'),
            ('高知県', '高知県'),
            ('福岡県', '福岡県'),
            ('佐賀県', '佐賀県'),
            ('長崎県', '長崎県'),
            ('熊本県', '熊本県'),
            ('大分県', '大分県'),
            ('宮崎県', '宮崎県'),
            ('鹿児島県', '鹿児島県'),
            ('沖縄県', '沖縄県')
        ],
        validators=[DataRequired(message="都道府県を選択してください。")]
    )
    
    city = StringField(
        '市区町村',
        validators=[DataRequired(message="市区町村を入力してください。"), Length(min=2, max=255, message="市区町村は2～255文字で入力してください。")]
    )
    address = StringField(
        'それ以降の住所',
        validators=[DataRequired(message="住所を入力してください。"), Length(min=2, max=255, message="住所は2～255文字で入力してください。")]
    )
    company_phone = StringField(
        '法人電話番号',
        validators=[Optional(), Length(min=10, max=20, message="法人電話番号は10～20文字で入力してください。")]
    )
    
    industry = SelectField(
        '業種',
        choices=[
            ('ゼネコン', 'ゼネコン'),
            ('工務店', '工務店'),
            ('木工業', '木工業'),
            ('リフォーム業', 'リフォーム業'),
            ('内装工事業', '内装工事業'),
            ('ハウスメーカー', 'ハウスメーカー'),
            ('専門職業(一人親方)', '専門職業(一人親方)'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    job_title = SelectField(
        '職種',
        choices=[
            ('木工大工', '木工大工'),
            ('ボード施工', 'ボード施工'),
            ('床施工', '床施工'),
            ('軽量鉄骨施工', '軽量鉄骨施工'),
            ('電気設備', '電気設備'),
            ('衛生設備', '衛生設備'),
            ('クロス施工', 'クロス施工'),
            ('左官', '左官'),
            ('塗装', '塗装'),
            ('屋根施工', '屋根施工'),
            ('外壁施工', '外壁施工'),
            ('解体', '解体'),
            ('外構施工', '外構施工'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    
    without_approval = BooleanField('リクエスト受け取り時、承認をスキップする')
    
    contact_name = StringField(
        '担当者名',
        validators=[DataRequired(message="担当者名を入力してください。")],
        render_kw={"autocomplete": "name", "readonly": True}
    )
    contact_phone = StringField(
        '担当者電話番号',
        validators=[DataRequired(message="担当者電話番号を入力してください。")],
        render_kw={"autocomplete": "tel"}
    )
    
    line_id = StringField(
        'LINE ID',
        validators=[Optional(), Length(min=2, max=100, message="LINE IDは2～100文字で入力してください。")]
    )
    
    submit = SubmitField('プロフィールを更新')
    
    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        if current_user.business_structure != '2':
            if not self.company_phone.data:
                self.company_phone.errors.append("法人電話番号を入力してください。")
                return False
            if not self.industry.data or self.industry.data == '':
                self.industry.errors.append("業種を選択してください。")
                return False
            if not self.job_title.data or self.job_title.data == '':
                self.job_title.errors.append("職種を選択してください。")
                return False
        return True

class RequestMaterialForm(FlaskForm):
    handover_location = SelectField(
        '受け渡し場所',
        choices=[
            ('', '選択してください'),
            ('指定なし', '指定なし'),
            ('現場', '現場'),
            ('店舗', '店舗'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    submit = SubmitField('リクエスト送信')

class RequestWantedMaterialForm(FlaskForm):
    submit = SubmitField('リクエスト送信')

class CancelRequestForm(FlaskForm):
    submit = SubmitField('リクエスト取り消し')

class CompleteMatchForm(FlaskForm):
    submit = SubmitField('完了')

class AcceptRequestMaterialForm(FlaskForm):
    submit = SubmitField('受け入れる')

class AcceptRequestWantedForm(FlaskForm):
    submit = SubmitField('受け入れる')

class DeleteHistoryForm(FlaskForm):
    submit = SubmitField('履歴削除')

class SiteForm(FlaskForm):
    site_prefecture = StringField('Prefecture', validators=[DataRequired(message="都道府県を入力してください。")])
    site_city = StringField('City', validators=[DataRequired(message="市区町村を入力してください。")])
    site_address = StringField('Address', validators=[DataRequired(message="住所を入力してください。")])
    participants = SelectMultipleField(
        'Participants',
        choices=[
            ('', '選択してください'),
            ('従業員', '従業員'),
            ('外部委託', '外部委託'),
            ('その他', 'その他')
        ],
        validators=[Optional()]
    )
    submit = SubmitField('Register Site')

class BulkMaterialForm(FlaskForm):
    # 端材エントリーを10個デフォルトで表示
    materials = FieldList(FormField(MaterialForm), min_entries=10, max_entries=10)
    submit = SubmitField('一括登録')

    def validate(self):
        overall_valid = True
        valid_entries = 0  # material_type が有効なエントリーの数

        # まず、各サブフォームの built-in バリデーションは実行済みなので、
        # ここでエラー内容を調整していきます。
        for index, subform in enumerate(self.materials):
            # material_type の値が未選択（例："選択してください"）の場合
            if subform.material_type.data == "選択してください" or not subform.material_type.data:
                if index == 0:
                    # 最初のエントリーは必須とするので、エラーをそのまま残す
                    overall_valid = False
                else:
                    # 2件目以降の場合は、material_type に対するエラーを消去し、
                    # 数量と締め切りのチェックもスキップする
                    subform.material_type.errors = []
                    subform.quantity.errors = []
                    subform.deadline.errors = []
            else:
                # material_type が有効な場合は、エントリーを有効とカウント
                valid_entries += 1
                # 数量・締め切りは必須なので、空の場合はエラー追加
                if not subform.quantity.data:
                    subform.quantity.errors.append("数量は必須です。")
                    overall_valid = False
                if not subform.deadline.data:
                    subform.deadline.errors.append("締め切り日時は必須です。")
                    overall_valid = False

        # すべてのエントリーで material_type が未選択の場合は全体エラー
        if valid_entries == 0:
            self.materials.errors.append("少なくとも1つのエントリーで端材の種類を選択してください。")
            overall_valid = False

        return overall_valid
