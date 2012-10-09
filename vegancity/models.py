from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q

import geocode
import shlex

TAG_LIST = (
    ('chinese', 'Chinese'),
    ('thai', 'Thai'),
    ('mexican', 'Mexican'),
    ('pizza', 'Pizza'),
    ('middle_eastern', 'Middle Eastern'),
    ('southern', 'Southern'),
    ('indian', 'Indian'),
    ('bar_food', 'Bar Food'),
    ('fast_food', 'Fast Food'),
    ('cheese_steaks', 'Cheese Steaks'),
    ('sandwiches', 'Sandwiches'),
    ('coffeehouse', 'Coffeehouse'),
    ('food_cart', 'Food Cart'),
    ('cash_only', 'Cash Only'),
    ('delivery','Offers Delivery'),
    ('open_late', 'Open after 10pm')
    )

VEG_LEVELS = (
    (1, "100% Vegan"),
    (2, "Vegetarian - Mostly Vegan"),
    (3, "Vegetarian - Hardly Vegan"),
    (4, "Not Vegetarian"),
    (5, "Beware!"),
    )
    
RATINGS = tuple((i, i) for i in range(1, 5))


class BlogEntry(models.Model):
    title = models.CharField(max_length=255)
    entry_date = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(User)
    text = models.TextField()

    class Meta:
        ordering = ('entry_date',)

    def __unicode__(self):
        return self.title

class QueryString(models.Model):
    value = models.CharField(max_length=255)
    entry_date = models.DateTimeField(auto_now_add=True)
    rank_results = models.CharField(max_length=100, null=True, blank=True)

    def __unicode__(self):
        return self.value

class Tag(models.Model):
    name = models.CharField(max_length=30)

    def __unicode__(self):
        return self.name

class VendorManager(models.Manager):
    "Manager class for handling searches by vendor."

    def get_query_set(self):
        "Changing initial queryset to ignore approved."
        # TODO - explore bugs this could cause!
        normal_qs = super(VendorManager, self).get_query_set()
        new_qs = normal_qs.filter(approved=True)
        return new_qs

    def pending_approval(self):
        """returns all vendors that are not approved, which are
        otherwise impossible to get in a normal query (for now)."""
        normal_qs = super(VendorManager, self).get_query_set()
        pending = normal_qs.filter(approved=False)
        return pending
        

    def tags_search(self, query):
        """Search vendors by tag.

Takes a query, breaks it into tokens, searches for tags
that contain the token.  If any of the tokens match any
tags, return all the orgs with that tag."""
        tokens = shlex.split(query)
        q_builder = Q()
        for token in tokens:
            q_builder = q_builder | Q(name__icontains=token)
        tag_matches = Tag.objects.filter(q_builder)
        vendors = set()
        for tag in tag_matches:
            for vendor in tag.vendor_set.all():
                vendors.add(vendor)
        vendor_count = len(vendors)
        summary_string = ('Found %d results with tags matching "%s".' 
                          % (vendor_count, ", ".join(tokens)))
        return {
            'count' : vendor_count, 
            'summary_statement' : summary_string, 
            'vendors':vendors
            }

    def name_search(self, query):
        """Search vendors by name.

Takes a query, breaks it into tokens, searches for names
that contain the token.  If any of the tokens match any
names, return all the orgs with that name."""
        tokens = shlex.split(query)
        q_builder = Q()
        for token in tokens:
            q_builder |= Q(name__icontains=token)
        vendors = self.filter(q_builder)
        vendor_count = vendors.count()
        summary_string = ('Found %d results where name contains "%s".' 
                          % (vendor_count, " or ".join(tokens)))
        return {
            'count' : vendor_count,
            'summary_statement' : summary_string, 
            'vendors' : vendors
            }

    #TODO - replace with something better!
    def address_search(self, query):
        """ Search vendors by address.

THIS WILL BE CHANGED SO NOT WRITING DOCUMENTATION."""
        tokens = shlex.split(query)
        q_builder = Q()
        for token in tokens:
            q_builder |= Q(address__icontains=token)
        vendors = self.filter(q_builder)
        vendor_count = vendors.count()
        summary_string = ('Found %d results where address contains "%s".' 
                          % (vendor_count, " or ".join(tokens)))
        return {
            'count' : vendor_count, 
            'summary_statement' : summary_string, 
            'vendors':vendors
            }
        
class VeganDish(models.Model):
    name = models.CharField(max_length=50)
    vendor = models.ForeignKey('Vendor')
    
    def __unicode__(self):
        return self.name

class Review(models.Model):
    entry_date = models.DateTimeField(auto_now_add=True)
    vendor = models.ForeignKey('Vendor')
    entered_by = models.ForeignKey(User, blank=True, null=True)
    approved = models.BooleanField(default=False)
    best_vegan_dish = models.ForeignKey(VeganDish, blank=True, null=True)
    unlisted_vegan_dish = models.CharField("Favorite Dish (if not listed)", max_length=100,
                                           help_text="We'll work on getting it in the database so others know about it!")
    content = models.TextField()

    def __unicode__(self):
        return "%s -- %s" % (self.vendor.name, str(self.entry_date))

class Vendor(models.Model):
    "The main class for this application"
    name = models.CharField(max_length=200)
    entry_date = models.DateTimeField(auto_now_add=True)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True,)
    veg_level = models.IntegerField(choices=VEG_LEVELS, 
                                    blank=True, null=True,)
    food_rating = models.IntegerField(choices=RATINGS, 
                                      blank=True, null=True, )
    atmosphere_rating = models.IntegerField(choices=RATINGS, 
                                            blank=True, null=True,)
    latitude = models.FloatField(default=None, blank=True, null=True)
    longitude = models.FloatField(default=None, blank=True, null=True)
    approved = models.BooleanField(default=False)
    tags = models.ManyToManyField(Tag, null=True, blank=True)
    objects = VendorManager()

    def __unicode__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.address and not (self.latitude and self.longitude):
            geocode_result = geocode.geocode_address(self.address)
            if geocode_result:
                self.latitude, self.longitude = geocode_result
        super(Vendor, self).save(*args, **kwargs)

    def best_vegan_dish(self):
        dishes = VeganDish.objects.filter(vendor=self)
        print dishes
        if dishes:
            return max(dishes, key=lambda d: Review.objects.filter(best_vegan_dish=d).count())
        else:
            return None


    
