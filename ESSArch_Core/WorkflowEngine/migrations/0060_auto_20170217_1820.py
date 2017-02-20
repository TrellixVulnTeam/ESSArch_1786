# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-02-17 17:20
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('WorkflowEngine', '0059_processtask_time_created'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='processstep',
            options={'get_latest_by': 'time_created', 'ordering': ('parent_step_pos', 'time_created')},
        ),
        migrations.AlterModelOptions(
            name='processtask',
            options={'get_latest_by': 'time_created'},
        ),
    ]
