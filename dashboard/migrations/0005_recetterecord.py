from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0004_rename_first_name_usersrecord_name_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='RecetteRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('amount', models.FloatField()),
            ],
        ),
    ]
