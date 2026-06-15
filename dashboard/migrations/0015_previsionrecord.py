from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0014_echeancerecord'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrevisionRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('amount', models.FloatField()),
            ],
        ),
    ]
