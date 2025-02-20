from marshmallow import Schema, fields, validate

class UserSchema(Schema):
    id = fields.Int(dump_only=True)
    username = fields.Str(required=True, validate=validate.Length(min=1))
    is_admin = fields.Bool()

class APIKeySchema(Schema):
    id = fields.Int(dump_only=True)
    key = fields.Str(dump_only=True)
    owner = fields.Str(required=True, validate=validate.Length(min=1))
    created_at = fields.DateTime(dump_only=True)
    revoked = fields.Bool()

class CreateMaterialSchema(Schema):
    type = fields.String(required=True, validate=validate.Length(min=1))
    size_1 = fields.Float(required=True)
    size_2 = fields.Float(required=True)
    size_3 = fields.Float(required=True)
    location = fields.String(required=False, allow_none=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))
    deadline = fields.DateTime(required=True)
    exclude_weekends = fields.Boolean(required=True)
    note = fields.String(required=False, allow_none=True)
    wood_type = fields.String(required=False, allow_none=True)
    board_material_type = fields.String(required=False, allow_none=True)
    panel_type = fields.String(required=False, allow_none=True)
    image = fields.Raw(required=False)  # 画像ファイル用

class EditMaterialSchema(Schema):
    type = fields.String(required=True, validate=validate.Length(min=1))
    size_1 = fields.Float(required=True)
    size_2 = fields.Float(required=True)
    size_3 = fields.Float(required=True)
    location = fields.String(required=False, allow_none=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))
    exclude_weekends = fields.Boolean(required=True)
    note = fields.String(required=False, allow_none=True)
    wood_type = fields.String(required=False, allow_none=True)
    board_material_type = fields.String(required=False, allow_none=True)
    panel_type = fields.String(required=False, allow_none=True)

class CreateWantedMaterialSchema(Schema):
    type = fields.String(required=True, validate=validate.Length(min=1))
    size_1 = fields.Float(required=True)
    size_2 = fields.Float(required=True)
    size_3 = fields.Float(required=True)
    location = fields.String(required=False, allow_none=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))
    deadline = fields.DateTime(required=True)
    exclude_weekends = fields.Boolean(required=True)
    note = fields.String(required=False, allow_none=True)
    wood_type = fields.String(required=False, allow_none=True)
    board_material_type = fields.String(required=False, allow_none=True)
    panel_type = fields.String(required=False, allow_none=True)

class EditWantedMaterialSchema(Schema):
    type = fields.String(required=True, validate=validate.Length(min=1))
    size_1 = fields.Float(required=True)
    size_2 = fields.Float(required=True)
    size_3 = fields.Float(required=True)
    location = fields.String(required=False, allow_none=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))
    exclude_weekends = fields.Boolean(required=True)
    note = fields.String(required=False, allow_none=True)
    wood_type = fields.String(required=False, allow_none=True)
    board_material_type = fields.String(required=False, allow_none=True)
    panel_type = fields.String(required=False, allow_none=True)