# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-02-04 14:32
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('WorkflowEngine', '0054_auto_20170119_1951'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='processtask',
            name='celery_id',
        ),
    ]
