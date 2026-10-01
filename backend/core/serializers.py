from rest_framework import serializers
from .models import *

READ_ONLY=['id','version','created_at','updated_at','number','completed_at','verified_at','source','returned_at','published_at','state']

def serializer_for(model):
    excluded = ['reporter_email','public_token_hash'] if model==WorkOrder else []
    readonly=READ_ONLY.copy()
    if model==BudgetScenario: readonly+=['lines','org_snapshot']
    if model==WorkOrder: readonly+=['status','schedule','occurrence']
    if model==Schedule: readonly+=[]
    meta=type('Meta',(),{'model':model,'exclude':excluded,'read_only_fields':readonly})
    def validate(self,attrs):
        if self.instance and 'org' in attrs and attrs['org'].pk!=self.instance.org_id:
            raise serializers.ValidationError({'org':'Ägande enhet kan inte ändras via vanlig redigering.'})
        obj=model(**attrs) if not self.instance else model.objects.get(pk=self.instance.pk)
        if self.instance:
            for k,v in attrs.items(): setattr(obj,k,v)
        # Django field/constraint validation follows inside the locked transaction.
        return attrs
    def represent(self,instance):
        data=serializers.ModelSerializer.to_representation(self,instance)
        data['org_name']=instance.org.name if hasattr(instance,'org') else ''
        if hasattr(instance,'asset_id'): data['asset_name']=instance.asset.name
        if isinstance(instance,Maintenance): data['budget']=str(instance.budget_for())
        if isinstance(instance,CostEntry): data['total']=str(instance.total)
        if isinstance(instance,WorkOrder): data['assigned_name']=instance.assigned_to.get_full_name() or instance.assigned_to.username if instance.assigned_to else None
        return data
    return type(model.__name__+'Serializer',(serializers.ModelSerializer,),{'Meta':meta,'validate':validate,'to_representation':represent})

class OrgSerializer(serializers.ModelSerializer):
    class Meta:
        model=OrgUnit
        fields='__all__'
        read_only_fields=['id','created_at','version']

class CommentSerializer(serializers.ModelSerializer):
    author_name=serializers.SerializerMethodField()
    def get_author_name(self,obj): return (obj.author.get_full_name() or obj.author.username) if obj.author else 'Anmälare'
    class Meta:
        model=WorkComment
        fields=['id','text','visibility','created_at','author_name']
        read_only_fields=['id','created_at','author_name']
