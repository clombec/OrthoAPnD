from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0002_alter_prosthesisrecord_impression_date'),
    ]

    operations = [
        migrations.CreateModel(
            name='UsersRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('patient_id', models.CharField(max_length=100, unique=True)),
                ('last_name', models.CharField(max_length=255)),
                ('first_name', models.CharField(max_length=255)),
            ],
        ),
    ]
