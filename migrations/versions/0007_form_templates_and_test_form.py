"""Add reusable Studio templates and an all-fields draft test form."""
from alembic import op
import sqlalchemy as sa


revision = "0007_form_templates_and_test_form"
down_revision = "0006_remove_legacy_asset_source_index"
branch_labels = None
depends_on = None


TEST_FIELDS = [
    {"id":"test-section-text","key":"","label":"Text and contact fields","type":"section","required":False,"help":"Test text entry, validation, placeholders, and responsive widths.","options":[],"width":"full","placeholder":"","icon":"1"},
    {"id":"test-short","key":"short_answer","label":"Short answer","type":"short_text","required":True,"help":"A required single-line response.","options":[],"width":"half","placeholder":"Enter a short answer","icon":"T"},
    {"id":"test-email","key":"contact_email","label":"Email address","type":"email","required":True,"help":"Must use a valid email format.","options":[],"width":"half","placeholder":"name@company.com","icon":"@"},
    {"id":"test-phone","key":"phone_number","label":"Phone number","type":"phone","required":False,"help":"Optional telephone input.","options":[],"width":"third","placeholder":"(555) 123-4567","icon":"☎"},
    {"id":"test-number","key":"quantity","label":"Quantity","type":"number","required":False,"help":"Accepts numeric values.","options":[],"width":"third","placeholder":"1","icon":"#"},
    {"id":"test-date","key":"requested_date","label":"Requested date","type":"date","required":False,"help":"Test the date picker.","options":[],"width":"third","placeholder":"","icon":"□"},
    {"id":"test-long","key":"detailed_answer","label":"Detailed answer","type":"long_text","required":True,"help":"Test a multi-line response.","options":[],"width":"full","placeholder":"Provide a detailed answer","icon":"≡"},
    {"id":"test-section-choice","key":"","label":"Dropdowns and choices","type":"section","required":False,"help":"Test every choice control and its configured options.","options":[],"width":"full","placeholder":"","icon":"2"},
    {"id":"test-dropdown","key":"dropdown_choice","label":"Dropdown with multiple options","type":"select","required":True,"help":"Open this dropdown and select one of five options.","options":["Laptop","Desktop","Monitor","Mobile phone","Other"],"width":"half","placeholder":"Select a device type","icon":"⌄"},
    {"id":"test-multiple","key":"multiple_choices","label":"Multi-select choices","type":"multi_select","required":False,"help":"Select one or more available services.","options":["Email","Microsoft Teams","VPN","Shared drive","Printing"],"width":"half","placeholder":"Choose services","icon":"☷"},
    {"id":"test-cards","key":"card_choice","label":"Visual choice cards","type":"choice_cards","required":True,"help":"Choose one visual card.","options":["Hardware","Software","Access","Network","Other"],"width":"full","placeholder":"","icon":"▦"},
    {"id":"test-radio","key":"impact","label":"Radio group","type":"radio","required":True,"help":"Choose one impact level.","options":["Low","Medium","High"],"width":"half","placeholder":"","icon":"◉"},
    {"id":"test-checkbox","key":"confirmation","label":"I confirm the information is ready for testing.","type":"checkbox","required":True,"help":"Required confirmation checkbox.","options":[],"width":"half","placeholder":"","icon":"✓"},
    {"id":"test-section-data","key":"","label":"ITSM data fields","type":"section","required":False,"help":"Test live people, assets, and time controls.","options":[],"width":"full","placeholder":"","icon":"3"},
    {"id":"test-user","key":"requested_for","label":"Person","type":"user","required":False,"help":"Loads active requesters from ITSM.","options":[],"width":"third","placeholder":"Choose a person","icon":"♙"},
    {"id":"test-asset","key":"affected_asset","label":"Asset","type":"asset","required":False,"help":"Loads available assets from the inventory.","options":[],"width":"third","placeholder":"Choose an asset","icon":"◇"},
    {"id":"test-time","key":"preferred_time","label":"Preferred time","type":"time","required":False,"help":"Test the time picker.","options":[],"width":"third","placeholder":"","icon":"◷"},
]


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("form_definitions")}
    if "is_template" not in columns:
        op.add_column("form_definitions", sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.create_index("ix_form_definitions_is_template", "form_definitions", ["is_template"])

    # Fresh installations already have the current model schema because 0001
    # creates Base.metadata. Reflect it so required columns added by later
    # releases are populated during this historical seed migration.
    forms = sa.Table("form_definitions", sa.MetaData(), autoload_with=bind)
    for organization_id in bind.execute(sa.text("SELECT id FROM organizations")).scalars().all():
        exists = bind.scalar(sa.select(sa.func.count()).select_from(forms).where(
            forms.c.organization_id == organization_id, forms.c.slug == "studio-field-test"))
        if not exists:
            bind.execute(forms.insert().values(
                organization_id=organization_id, slug="studio-field-test", name="Studio Field Test Form",
                description="Draft form for testing every Studio field, dropdown, layout, and validation behavior.",
                category="Studio Testing", icon="form", fields=TEST_FIELDS, active=True,
                is_template=False, published=False, form_type="service_request",
                portal_visible=False, default_for_type=False, requester_layout=[], technician_layout=[],
                lifecycle_state="draft", version=1, created_at=sa.func.now(), updated_at=sa.func.now()))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM form_definitions WHERE slug = 'studio-field-test' AND published = FALSE"))
    columns = {column["name"] for column in sa.inspect(bind).get_columns("form_definitions")}
    if "is_template" in columns:
        op.drop_index("ix_form_definitions_is_template", table_name="form_definitions")
        op.drop_column("form_definitions", "is_template")
