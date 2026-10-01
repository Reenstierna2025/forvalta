from django.db import migrations

TABLES=['core_auditevent','core_orgrevision','core_reportsnapshot','core_document','core_costentry','core_reading','core_workcomment']

def forwards(apps,schema_editor):
    connection=schema_editor.connection
    if connection.vendor=='postgresql':
        with connection.cursor() as c:
            c.execute("CREATE FUNCTION forvalta_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Record is append-only'; END $$")
            for table in TABLES:
                c.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION forvalta_immutable()')
            c.execute("CREATE FUNCTION forvalta_budget_lock() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.state = 'published' THEN RAISE EXCEPTION 'Published budget is immutable'; END IF; IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$")
            c.execute('CREATE TRIGGER budget_lock BEFORE UPDATE OR DELETE ON core_budgetscenario FOR EACH ROW EXECUTE FUNCTION forvalta_budget_lock()')
    elif connection.vendor=='sqlite':
        with connection.cursor() as c:
            for table in TABLES:
                for action in ['UPDATE','DELETE']:
                    c.execute(f"CREATE TRIGGER {table}_immutable_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Record is append-only'); END")
            for action in ['UPDATE','DELETE']:
                c.execute(f"CREATE TRIGGER budget_lock_{action} BEFORE {action} ON core_budgetscenario WHEN OLD.state='published' BEGIN SELECT RAISE(ABORT,'Published budget is immutable'); END")

def backwards(apps,schema_editor):
    connection=schema_editor.connection
    with connection.cursor() as c:
        if connection.vendor=='postgresql':
            for table in TABLES:c.execute(f'DROP TRIGGER IF EXISTS {table}_immutable ON {table}')
            c.execute('DROP TRIGGER IF EXISTS budget_lock ON core_budgetscenario');c.execute('DROP FUNCTION IF EXISTS forvalta_immutable()');c.execute('DROP FUNCTION IF EXISTS forvalta_budget_lock()')
        elif connection.vendor=='sqlite':
            for table in TABLES:
                for action in ['UPDATE','DELETE']:c.execute(f'DROP TRIGGER IF EXISTS {table}_immutable_{action}')
            for action in ['UPDATE','DELETE']:c.execute(f'DROP TRIGGER IF EXISTS budget_lock_{action}')

class Migration(migrations.Migration):
    dependencies=[('core','0001_initial')]
    operations=[migrations.RunPython(forwards,backwards)]
