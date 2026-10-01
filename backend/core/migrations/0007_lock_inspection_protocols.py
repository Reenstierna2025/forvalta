from django.db import migrations

def forward(apps,schema_editor):
    with schema_editor.connection.cursor() as c:
        if schema_editor.connection.vendor=='postgresql':
            c.execute("CREATE FUNCTION forvalta_inspection_lock() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.state='published' THEN RAISE EXCEPTION 'Published protocol is immutable'; END IF; IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$")
            c.execute('CREATE TRIGGER inspection_lock BEFORE UPDATE OR DELETE ON core_inspection FOR EACH ROW EXECUTE FUNCTION forvalta_inspection_lock()')
        elif schema_editor.connection.vendor=='sqlite':
            for action in ['UPDATE','DELETE']:c.execute(f"CREATE TRIGGER inspection_lock_{action} BEFORE {action} ON core_inspection WHEN OLD.state='published' BEGIN SELECT RAISE(ABORT,'Published protocol is immutable'); END")

def backward(apps,schema_editor):
    with schema_editor.connection.cursor() as c:
        if schema_editor.connection.vendor=='postgresql':
            c.execute('DROP TRIGGER IF EXISTS inspection_lock ON core_inspection');c.execute('DROP FUNCTION IF EXISTS forvalta_inspection_lock()')
        elif schema_editor.connection.vendor=='sqlite':
            for action in ['UPDATE','DELETE']:c.execute(f'DROP TRIGGER IF EXISTS inspection_lock_{action}')

class Migration(migrations.Migration):
    dependencies=[('core','0006_alter_inspection_follow_up_of_and_more')]
    operations=[migrations.RunPython(forward,backward)]
