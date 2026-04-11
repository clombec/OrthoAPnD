from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0005_recetterecord'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='RecetteRecord',
            new_name='IncomeRecord',
        ),
    ]
