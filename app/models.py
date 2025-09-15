# app/models.py

from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableDict, MutableList
import pytz
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import event
from sqlalchemy.orm import joinedload
from app.utils.s3_uploader import build_s3_url
import enum

# タイムゾーンの設定
JST = pytz.timezone('Asia/Tokyo')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Association table for user favorite terminals
favorite_terminals = db.Table('favorite_terminals',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('terminal_id', db.Integer, db.ForeignKey('terminals.id'), primary_key=True)
)

# Association table for user favorite lecturers
favorite_lecturers = db.Table('favorite_lecturers',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('lecturer_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)

# Terminalモデル
class Terminal(db.Model):
    __tablename__ = 'terminals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    prefecture = db.Column(db.String(50), nullable=False)
    zip_code = db.Column(db.String(10), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    room_count = db.Column(db.Integer, nullable=False)
    is_favorite = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))

    # リレーションシップ
    user = db.relationship('User', back_populates='terminals', foreign_keys='Terminal.user_id')
    rooms = db.relationship('Room', back_populates='terminal', lazy=True)
    reservations = db.relationship('Reservation', back_populates='terminal', lazy=True)

    # 新しいリレーションシップの追加
    affiliated_users = db.relationship('User', back_populates='affiliated_terminal', lazy='dynamic', foreign_keys='User.affiliated_terminal_id')

    def __repr__(self):
        return f"<Terminal {self.name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'address': self.address,
            'city': self.city,
            'prefecture': self.prefecture,
            'zip_code': self.zip_code,
            'phone': self.phone,
            'room_count': self.room_count,
            'is_favorite': self.is_favorite,
            'created_at': self.created_at.isoformat(),
        }

# Userモデル
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    company_name = db.Column(db.String(120), nullable=False)
    prefecture = db.Column(db.String(20), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    company_phone = db.Column(db.String(20), nullable=False)
    industry = db.Column(db.String(100), nullable=False)
    job_title = db.Column(db.String(100), nullable=False)
    without_approval = db.Column(db.Boolean, nullable=False, default=False)
    contact_name = db.Column(db.String(100), nullable=False)  # usernameの代わりに使用
    contact_phone = db.Column(db.String(20), nullable=False)
    line_id = db.Column(db.String(50), nullable=True)
    lecture_flug = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))
    affiliated_terminal_id = db.Column(db.Integer, db.ForeignKey('terminals.id'), nullable=True)
    is_terminal_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    last_seen = db.Column(db.DateTime, nullable=True)
    business_structure = db.Column(db.Integer, nullable=False, default=0)
    device_tokens    = db.Column(
        MutableList.as_mutable(ARRAY(db.String)),
        nullable=True
    )
    # リレーションシップ
    materials = db.relationship('Material', back_populates='owner', lazy=True)
    wanted_materials = db.relationship('WantedMaterial', back_populates='owner', lazy=True)
    lectures = db.relationship('Lecture', back_populates='lecturer', lazy=True, foreign_keys='Lecture.lecturer_id')
    reservations = db.relationship('Reservation', back_populates='user', lazy=True, foreign_keys='Reservation.user_id')
    terminals = db.relationship('Terminal', back_populates='user', lazy=True, foreign_keys='Terminal.user_id')
    working_hours = db.relationship('WorkingHours', back_populates='user', lazy=True)

    # 新しいリレーションシップの追加
    affiliated_terminal = db.relationship('Terminal', back_populates='affiliated_users', foreign_keys=[affiliated_terminal_id])

    # Favorite Terminals relationship
    favorite_terminals = db.relationship(
        'Terminal',
        secondary=favorite_terminals,
        backref=db.backref('favorited_by_users_terminals', lazy='dynamic'),
        lazy='dynamic'
    )

    favorite_lecturers = db.relationship(
        'User',
        secondary=favorite_lecturers,
        primaryjoin=(favorite_lecturers.c.user_id == id),
        secondaryjoin=(favorite_lecturers.c.lecturer_id == id),
        backref=db.backref('favorited_by_users_lecturers', lazy='dynamic'),
        lazy='dynamic'
    )

    def set_password(self, password):
        self.password = generate_password_hash(password)  # 修正: password_hash -> password

    def check_password(self, password):
        return check_password_hash(self.password, password)  # 修正: password_hash -> password

    def get_reset_token(self, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token, max_age=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token, max_age=max_age)['user_id']
        except:
            return None
        return User.query.get(user_id)

    def __repr__(self):
        return f"<User {self.email}>"

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'company_name': self.company_name,
            'prefecture': self.prefecture,
            'city': self.city,
            'address': self.address,
            'company_phone': self.company_phone,
            'industry': self.industry,
            'job_title': self.job_title,
            'without_approval': self.without_approval,
            'contact_name': self.contact_name,
            'contact_phone': self.contact_phone,
            'line_id': self.line_id,
            'lecture_flug': self.lecture_flug,
            'created_at': self.created_at.isoformat(),
            'affiliated_terminal_id': self.affiliated_terminal_id,
            'is_terminal_admin': self.is_terminal_admin,
            'is_admin': self.is_admin,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'business_structure': self.business_structure,
        }

# Materialモデル
class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    type = db.Column(db.String(100), nullable=False)
    size_1 = db.Column(db.Float, nullable=False)
    size_2 = db.Column(db.Float, nullable=False)
    size_3 = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(200), nullable=False, default="")
    quantity = db.Column(db.Integer, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))
    exclude_weekends = db.Column(db.Boolean, nullable=False, default=False)
    image = db.Column(db.String(200), nullable=True, default='no_image.png')
    note = db.Column(db.Text, nullable=True)
    matched = db.Column(db.Boolean, default=False)
    matched_at = db.Column(db.DateTime, nullable=True)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    pre_completed    = db.Column(db.Boolean, default=False)
    pre_completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))
    deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    # 新しく追加されたカラム: site_id
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=True)
    site = db.relationship('Site', back_populates='materials')

    # 新しいカラムの追加
    wood_type = db.Column(db.String(50), nullable=True)
    board_material_type = db.Column(db.String(50), nullable=True)
    panel_type = db.Column(db.String(50), nullable=True)

    # 新規追加: m_prefecture, m_city, m_address
    m_prefecture = db.Column(db.String(20), nullable=False, default='')
    m_city = db.Column(db.String(100), nullable=False, default='')
    m_address = db.Column(db.String(200), nullable=False, default='')

    # リレーションシップ
    owner = db.relationship('User', back_populates='materials')
    requests = db.relationship('Request', back_populates='material', lazy=True)

    group_id = db.Column(db.Integer,
                         db.ForeignKey('user_groups.id'),
                         nullable=True)
    group = db.relationship('UserGroup', backref='materials')

    def __repr__(self):
        return f"<Material {self.type} at {self.location} site_id={self.site_id}>"

    def to_dict(self, include_user: bool = False):
        d = {
            'id': self.id,
            'user_id': self.user_id,
            'type': self.type,
            'size_1': self.size_1,
            'size_2': self.size_2,
            'size_3': self.size_3,
            'location': self.location,
            'quantity': self.quantity,
            'deadline': self.deadline.isoformat(),
            'exclude_weekends': self.exclude_weekends,
            'image': self.image,
            'note': self.note,
            'matched': self.matched,
            'matched_at': self.matched_at.isoformat() if self.matched_at else None,
            'completed': self.completed,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat(),
            'deleted': self.deleted,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
            'site_id': self.site_id,
            'wood_type': self.wood_type,
            'board_material_type': self.board_material_type,
            'panel_type': self.panel_type,
            'm_prefecture': self.m_prefecture,
            'm_city': self.m_city,
            'm_address': self.m_address,
            'group_id': self.group_id,
        }
        if include_user:
            d['user'] = self.owner.to_dict() if self.owner else None
        return d

@property
def image_url(self) -> str:
    """
    DB に保存されているオブジェクトキーからフル URL を返す
     テンプレート側は material.image_url を使えば移行コスト 0
    """
    if not self.image or self.image == 'no_image.png':
        return build_s3_url('materials/no_image.png')
    return build_s3_url(self.image)

# WantedMaterialモデル
class WantedMaterial(db.Model):
    __tablename__ = 'wanted_materials'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    type = db.Column(db.String(100), nullable=False)
    size_1 = db.Column(db.Float, nullable=False)
    size_2 = db.Column(db.Float, nullable=False)
    size_3 = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(200), nullable=False, default="")
    quantity = db.Column(db.Integer, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))
    exclude_weekends = db.Column(db.Boolean, nullable=False, default=False)
    note = db.Column(db.Text, nullable=True)
    matched = db.Column(db.Boolean, default=False)
    matched_at = db.Column(db.DateTime, nullable=True)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    pre_completed    = db.Column(db.Boolean, default=False)
    pre_completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))
    deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    # その他のカラムとリレーションシップ
    wood_type = db.Column(db.String(50), nullable=True)
    board_material_type = db.Column(db.String(50), nullable=True)
    panel_type = db.Column(db.String(50), nullable=True)

    # 新規追加: wm_prefecture, wm_city, wm_address
    wm_prefecture = db.Column(db.String(20), nullable=False, default='')
    wm_city = db.Column(db.String(100), nullable=False, default='')
    wm_address = db.Column(db.String(200), nullable=False, default='')

    owner = db.relationship('User', back_populates='wanted_materials')
    requests = db.relationship('Request', back_populates='wanted_material', lazy=True)

    def __repr__(self):
        owner_email = self.owner.email if self.owner is not None else "unknown"
        return f"<WantedMaterial {self.type} desired by {owner_email}>"

    def to_dict(self, include_user: bool = False):
        d = {
            'id': self.id,
            'user_id': self.user_id,
            'type': self.type,
            'size_1': self.size_1,
            'size_2': self.size_2,
            'size_3': self.size_3,
            'location': self.location,
            'quantity': self.quantity,
            'deadline': self.deadline.isoformat(),
            'exclude_weekends': self.exclude_weekends,
            'note': self.note,
            'matched': self.matched,
            'matched_at': self.matched_at.isoformat() if self.matched_at else None,
            'completed': self.completed,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat(),
            'deleted': self.deleted,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
            'wood_type': self.wood_type,
            'board_material_type': self.board_material_type,
            'panel_type': self.panel_type,
            'wm_prefecture': self.wm_prefecture,
            'wm_city': self.wm_city,
            'wm_address': self.wm_address,
        }
        if include_user:
            d['user'] = self.owner.to_dict() if self.owner else None
        return d

# Requestモデル
class Request(db.Model):
    __tablename__ = 'requests'
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('materials.id'), nullable=True)
    wanted_material_id = db.Column(db.Integer, db.ForeignKey('wanted_materials.id'), nullable=True)
    requester_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    requested_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="Pending")
    requested_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))

    # 新規カラム
    accepted_at = db.Column(db.DateTime, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # リレーションシップ
    material = db.relationship('Material', back_populates='requests')
    wanted_material = db.relationship('WantedMaterial', back_populates='requests')
    requester_user = db.relationship('User', foreign_keys=[requester_user_id], backref='sent_requests')
    requested_user = db.relationship('User', foreign_keys=[requested_user_id], backref='received_requests')

    def accept(self):
        self.status = 'Accepted'
        self.accepted_at = datetime.now(JST)
        if self.material:
            self.material.matched = True
            self.material.matched_at = datetime.now(JST)
            db.session.add(self.material)
        if self.wanted_material:
            self.wanted_material.matched = True
            self.wanted_material.matched_at = datetime.now(JST)
            db.session.add(self.wanted_material)
        db.session.commit()

    def reject_other_requests(self):
        other_requests = []
        if self.material:
            other_requests = Request.query.filter(
                Request.material_id == self.material_id,
                Request.id != self.id,
                Request.status == "Pending"
            ).all()
        if self.wanted_material:
            other_requests = Request.query.filter(
                Request.wanted_material_id == self.wanted_material_id,
                Request.id != self.id,
                Request.status == "Pending"
            ).all()
        for req in other_requests:
            req.status = 'Rejected'
            req.rejected_at = datetime.now(JST)
            db.session.add(req)
        db.session.commit()


    def get_roles_for_material(mat, user_id: int) -> dict[str, bool]:
        """
        Material 用 – accepted な Request を 1 件探して役割を返す
        正:  オーナー(requested_user) = Sender
            リクエスト送信者(requester_user) = Receiver
        """
        req = (Request.query
            .options(joinedload(Request.requester_user))
            .filter_by(material_id=mat.id, status='Accepted')
            .first())

        return {
            'is_sender':   bool(req and req.requester_user_id == user_id),
            'is_receiver': bool(req and req.requested_user_id == user_id),
        }
    def get_roles_for_wanted(wanted, user_id: int) -> dict[str, bool]:
        """WantedMaterial 用 –  accepted な Request を 1 件探して役割を返す"""
        req = (Request.query
            .options(joinedload(Request.requester_user))
            .filter_by(wanted_material_id=wanted.id, status='Accepted')
            .first())
        return {
            'is_sender':   bool(req and req.requester_user_id  == user_id),
            'is_receiver': bool(req and req.requested_user_id == user_id),
        }

    def to_dict(self):
        return {
            'id': self.id,
            'material_id': self.material_id,
            'wanted_material_id': self.wanted_material_id,
            'requester_user_id': self.requester_user_id,
            'requested_user_id': self.requested_user_id,
            'status': self.status,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'accepted_at': self.accepted_at.isoformat() if self.accepted_at else None,
            'rejected_at': self.rejected_at.isoformat() if self.rejected_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }

    def __repr__(self):
        return f"<Request {self.id} from {self.requester_user.email} to {self.requested_user.email}>"

# WantedMaterial の更新後に、完了日時を Request に反映するイベントリスナー
@event.listens_for(WantedMaterial, 'after_update')
def update_request_completed_at(mapper, connection, target):
    # target: 更新された WantedMaterial インスタンス
    if target.completed and target.completed_at:
        connection.execute(
            Request.__table__.update()
            .where(Request.wanted_material_id == target.id)
            .values(completed_at=target.completed_at)
        )

# Roomモデル
class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    terminal_id = db.Column(db.Integer, db.ForeignKey('terminals.id'), nullable=False)
    room_number = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))

    # リレーションシップ
    terminal = db.relationship('Terminal', back_populates='rooms')
    reservations = db.relationship('Reservation', back_populates='room', lazy=True)

    def __repr__(self):
        return f"<Room {self.room_number} at Terminal {self.terminal.name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'terminal_id': self.terminal_id,
            'room_number': self.room_number,
            'created_at': self.created_at.isoformat(),
        }

# Reservationモデル
class Reservation(db.Model):
    __tablename__ = 'reservations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    terminal_id = db.Column(db.Integer, db.ForeignKey('terminals.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # リクエスト関連のカラムを追加
    requested_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    requested_time = db.Column(db.Time, nullable=True)
    request_flag = db.Column(db.Boolean, default=False, nullable=False)
    accepted_time = db.Column(db.DateTime, nullable=True)
    accepted_flag = db.Column(db.Boolean, default=False, nullable=False)
    
    # 追加するカラム
    canceled = db.Column(db.Boolean, default=False, nullable=False)
    
    # リレーションシップの設定
    user = db.relationship('User', back_populates='reservations', foreign_keys=[user_id])
    room = db.relationship('Room', back_populates='reservations')
    terminal = db.relationship('Terminal', back_populates='reservations')
    lecturer = db.relationship('User', foreign_keys=[lecturer_id], backref='lecturer_reservations')
    requested_user = db.relationship('User', foreign_keys=[requested_user_id], backref='requested_reservations')

    def __repr__(self):
        return f"<Reservation {self.id} for {self.room.room_number} on {self.date}>"

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'room_id': self.room_id,
            'terminal_id': self.terminal_id,
            'date': self.date.isoformat(),
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'lecturer_id': self.lecturer_id,
            'requested_user_id': self.requested_user_id,
            'requested_time': self.requested_time.isoformat() if self.requested_time else None,
            'request_flag': self.request_flag,
            'accepted_time': self.accepted_time.isoformat() if self.accepted_time else None,
            'accepted_flag': self.accepted_flag,
            'canceled': self.canceled,
        }

# Lectureモデル
class Lecture(db.Model):
    __tablename__ = 'lectures'
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="Pending")
    video_url = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))
    
    # リレーションシップ
    lecturer = db.relationship('User', back_populates='lectures', foreign_keys=[lecturer_id])
    reservation = db.relationship('Reservation', backref='lecture', lazy=True)
    
    def __repr__(self):
        return f"<Lecture {self.id} by {self.lecturer.contact_name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'reservation_id': self.reservation_id,
            'lecturer_id': self.lecturer_id,
            'status': self.status,
            'video_url': self.video_url,
            'created_at': self.created_at.isoformat(),
        }

# WorkingHoursモデル
class WorkingHours(db.Model):
    __tablename__ = 'working_hours'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    time_slots = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST), nullable=False)
    
    # リレーションシップ
    user = db.relationship('User', back_populates='working_hours')

    def __repr__(self):
        return f"<WorkingHours {self.user.email} on {self.date}>"

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'date': self.date.isoformat(),
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'is_active': self.is_active,
            'time_slots': self.time_slots,
            'created_at': self.created_at.isoformat(),
        }

# Logモデル
class Log(db.Model):
    __tablename__ = 'sosa_log'
    sosa_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    device_info = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    
    def __repr__(self):
        return f"<Log {self.sosa_id} - {self.action}>"

    def to_dict(self):
        return {
            'sosa_id': self.sosa_id,
            'timestamp': self.timestamp.isoformat(),
            'user_id': self.user_id,
            'action': self.action,
            'details': self.details,
            'ip_address': self.ip_address,
            'device_info': self.device_info,
            'location': self.location,
        }

class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    
    # user1_id は必ず存在する前提ならNULL不可
    user1_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False
    )
    
    # user2_id は存在しないケースもあるならNULL可
    user2_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=True
    )
    
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))
    is_hidden = db.Column(db.Boolean, nullable=False, default=False)
    last_message = db.Column(db.Text, nullable=True)
    chat_token = db.Column(db.Text, nullable=True)

    user1 = db.relationship('User', foreign_keys=[user1_id], backref='conversations_as_user1')
    user2 = db.relationship('User', foreign_keys=[user2_id], backref='conversations_as_user2', lazy='joined')

    messages = db.relationship(
        'Message',
        back_populates='conversation',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    # ──────────────────────────────────────────────
    # チャット用トークン生成（itsdangerous 利用）
    # ──────────────────────────────────────────────
    def gen_chat_token(self, user_id: int, expires_sec: int = 86400) -> str:
        """
        引数: user_id = トークンを発行するユーザ
        戻り値: 署名付きトークン（base64 str）
        """
        s = Serializer(current_app.config["SECRET_KEY"])
        token = s.dumps({"cid": self.id, "uid": user_id}, salt="chat")

        # 直近トークンを DB に保持したい場合はここで上書き
        self.chat_token = token
        db.session.add(self)            # 変更をマーク
        # commit は呼び出し側でまとめて行う想定
        return token

    # もし user2_id が NULL でも unique_user_pair 制約をどうするか注意
    __table_args__ = (
        # 下記uniqueは user2_id がNULLの時どう扱われるか検討必要
        db.UniqueConstraint('user1_id', 'user2_id', name='unique_user_pair'),
    )

    def __init__(self, user1_id, user2_id, **kwargs):
        if user1_id < user2_id:
            self.user1_id = user1_id
            self.user2_id = user2_id
        else:
            self.user1_id = user2_id
            self.user2_id = user1_id
        super().__init__(**kwargs)
    
    def __repr__(self):
        return f"<Conversation between {self.user1.email} and {self.user2.email}>"

    def to_dict(self):
        return {
            'id': self.id,
            'user1_id': self.user1_id,
            'user2_id': self.user2_id,
            'created_at': self.created_at.isoformat(),
            'is_hidden': self.is_hidden
        }

# Messageモデル
class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=True)
    attachment = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(JST))
    edited = db.Column(db.Boolean, default=False, nullable=False)
    edited_at = db.Column(db.DateTime, nullable=True)
    
    conversation = db.relationship('Conversation', back_populates='messages')
    sender = db.relationship('User', backref='sent_messages', foreign_keys=[sender_id])
    
    def __repr__(self):
        return f"<Message {self.id} from {self.sender.email} at {self.timestamp}>"

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender_id': self.sender_id,
            'content': self.content,
            'attachment': self.attachment,
            'timestamp': self.timestamp.isoformat(),
            'edited': self.edited,
            'edited_at': self.edited_at.isoformat() if self.edited_at else None,
        }

# Siteモデル
class Site(db.Model):
    __tablename__ = 'site'
    id = db.Column(db.Integer, primary_key=True)
    registered_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    site_prefecture = db.Column(db.String(50), nullable=False)
    site_city = db.Column(db.String(100), nullable=False)
    site_address = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(350), nullable=False)
    registered_company = db.Column(db.String(120), nullable=False, default='')
    site_created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(JST))
    participants = db.Column(ARRAY(db.Integer), nullable=False, default=[])

    # リレーションシップ
    registered_user = db.relationship('User', backref='sites')
    materials = db.relationship('Material', back_populates='site')
    # wanted_materials = db.relationship('WantedMaterial', back_populates='site')  # 削除

    def __repr__(self):
        return f"<Site {self.site_address} registered by {self.registered_user.email}>"

    def to_dict(self):
        return {
            'id': self.id,
            'registered_user_id': self.registered_user_id,
            'site_prefecture': self.site_prefecture,
            'site_city': self.site_city,
            'site_address': self.site_address,
            'location': self.location,
            'registered_company': self.registered_company,
            'site_created_at': self.site_created_at.isoformat(),
            'participants': self.participants,
        }

# APIKeyモデル
class APIKey(db.Model):
    __tablename__ = 'api_keys'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_hex(32))
    owner = db.Column(db.String(100), nullable=False)  # APIキーの所有者（例: クライアント名）
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    revoked = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<APIKey {self.key} - {self.owner}>"

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'owner': self.owner,
            'created_at': self.created_at.isoformat(),
            'revoked': self.revoked,
        }

class GroupRole(str, enum.Enum):
    MEMBER = "member"
    ADMIN  = "admin"

class UserGroup(db.Model):
    __tablename__ = "user_groups"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    owner_user_id = db.Column(db.Integer,
                              db.ForeignKey("users.id", ondelete="CASCADE"),
                              nullable=False)
    description = db.Column(db.Text)
    created_at  = db.Column(db.DateTime(timezone=True),
                            default=datetime.now(JST),
                            nullable=False)
    deleted_at  = db.Column(db.DateTime(timezone=True))

    # ───── リレーション ─────
    owner   = db.relationship("User",
                              backref="owned_groups",
                              foreign_keys=[owner_user_id])
    members = db.relationship("GroupMembership",
                              back_populates="group",
                              cascade="all, delete-orphan")

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None

class GroupMembership(db.Model):
    __tablename__ = "group_memberships"

    group_id = db.Column(db.Integer,
                         db.ForeignKey("user_groups.id", ondelete="CASCADE"),
                         primary_key=True)
    user_id  = db.Column(db.Integer,
                         db.ForeignKey("users.id", ondelete="CASCADE"),
                         primary_key=True)


    role = db.Column(
        db.Enum(
            GroupRole,
            name="group_role",
            values_callable=lambda enum_cls: [e.value for e in enum_cls]  # ★追加
        ),
        nullable=False,
        server_default=GroupRole.MEMBER.value
    )

    joined_at = db.Column(db.DateTime(timezone=True),
                          default=datetime.now(JST),
                          nullable=False)

    # ───── リレーション ─────
    group = db.relationship("UserGroup", back_populates="members")
    user  = db.relationship("User",
                            backref="group_memberships")
