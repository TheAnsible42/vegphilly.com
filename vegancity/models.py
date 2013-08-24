# Copyright (C) 2012 Steve Lamb

# This file is part of Vegancity.

# Vegancity is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Vegancity is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Vegancity.  If not, see <http://www.gnu.org/licenses/>.

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from django.db.models.signals import m2m_changed

from django.db.models import Count

from django.template.defaultfilters import slugify
from django.core.exceptions import ValidationError

import collections

from vegancity import geocode, validators, email


class TagManager(models.Manager):

    def word_search(self, word):
        "takes a word and searches all tag names for that word"
        qs = self.filter(name__icontains=word)
        if not qs and word[-1] == 's':
            qs = self.filter(name__icontains=word[:-1])
        return qs

    def with_vendors(self, vendors=None):
        "filters tags to tags that actually have vendors"
        qs = self.all()
        if vendors:
            qs = qs.filter(vendor__in=vendors).distinct('name')
        else:
            annotated = self.annotate(num_vendors=Count('vendor'))
            qs = annotated.filter(num_vendors__gte=1)
        return qs

    def get_vendors(self, qs):
        results = set()
        for tag in qs:
            results = results.union(tag.vendor_set.all())
        return results


class _TagModel(models.Model):

    name = models.CharField(
        help_text="short name, all lowercase alphas, underscores for spaces",
        max_length=255, unique=True
        )
    description = models.CharField(
        help_text="Nicely formatted text.  About a sentence.",
        max_length=255
        )
    created = models.DateTimeField(auto_now_add=True, null=True)
    objects = TagManager()

    def __unicode__(self):
        return self.description

    def get_vendors(self):
        "returns all the vendors that are tagged with this tag."
        return self.vendor_set.all()

    class Meta:
        abstract = True
        get_latest_by = "created"
        ordering = ('name',)

#######################################
# SITE CLASSES
#######################################


class VegLevel(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    super_category = models.CharField(max_length=30,
                                      choices=(
                                          ('vegan', 'Vegan'),
                                          ('vegetarian', 'Vegetarian'),
                                          ('not_veg', 'Not Vegetarian')))

    def __unicode__(self):
        return "(%s) %s" % (self.super_category, self.description)

class NeighborhoodManager(models.Manager):

    def with_vendors(self):
        qs = self.all()
        qs = qs.annotate(vendor_count=Count('vendor'))\
               .filter(vendor_count__gt=0)
        return qs

class Neighborhood(models.Model):
    """Used for determining what neighborhood a vendor is in."""
    name = models.CharField(max_length=255, unique=True)
    created = models.DateTimeField(auto_now_add=True, null=True)

    objects = NeighborhoodManager()

    def __unicode__(self):
        return self.name

    class Meta:
        verbose_name = "Neighborhood"
        verbose_name_plural = "Neighborhoods"
        get_latest_by = "created"
        ordering = ('name',)


##########################################
# USER-RELATED MODELS
##########################################

class UserProfile(models.Model):
    user = models.ForeignKey(User, unique=True)
    mailing_list = models.BooleanField(default=False)
    karma_points = models.IntegerField(null=True, blank=True)
    bio = models.TextField(null=True, blank=True)


class BlogEntry(models.Model):
    "Blog entries. They get entered in the admin."
    title = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(User)
    body = models.TextField()

    class Meta:
        ordering = ('-created',)
        verbose_name = "Blog Entry"
        verbose_name_plural = "Blog Entries"
        get_latest_by = "created"

    def __unicode__(self):
        return self.title

    @models.permalink
    def get_absolute_url(self):
        return (reverse('blog_detail'), (str(self.id),))


##########################################
# VENDOR-RELATED MODELS
##########################################


class VeganDish(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created = models.DateTimeField(auto_now_add=True, null=True)

    def __unicode__(self):
        return self.name

    class Meta:
        get_latest_by = "created"
        ordering = ('name',)
        verbose_name = "Vegan Dish"
        verbose_name_plural = "Vegan Dishes"


class ReviewManager(models.Manager):
    "Manager class for handling searches by review."

    def pending_approval(self):
        """returns all reviews that are not approved, which are
        otherwise impossible to get in a normal query (for now)."""
        normal_qs = self.get_query_set()
        pending = normal_qs.filter(approved=False)
        return pending


class ApprovedReviewManager(ReviewManager):
    "Manager for approved reviews only."

    def get_query_set(self):
        "Changing initial queryset to ignore approved."
        normal_qs = super(ApprovedReviewManager, self).get_query_set()
        new_qs = normal_qs.filter(approved=True)
        return new_qs


class Review(models.Model):

    # CORE FIELDS
    vendor = models.ForeignKey('Vendor')
    author = models.ForeignKey(User)

    # ADMINISTRATIVE FIELDS
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    approved = models.BooleanField(default=False)
    objects = ReviewManager()
    approved_objects = ApprovedReviewManager()

    # DESCRIPTIVE FIELDS
    title = models.CharField(
        "Title of review (optional)",
        max_length=255, null=True, blank=True)
    food_rating = models.IntegerField(
        "How would you rate the food, overall?",
        choices=tuple((i, i) for i in range(1, 5)),
        blank=True, null=True,)
    atmosphere_rating = models.IntegerField(
        "How would you rate the atmosphere?",
        choices=tuple((i, i) for i in range(1, 5)),
        blank=True, null=True,)
    best_vegan_dish = models.ForeignKey(
        'VeganDish',
        verbose_name="Favorite Vegan Dish",
        blank=True, null=True)
    unlisted_vegan_dish = models.CharField(max_length=100,
                                           blank=True, null=True)
    suggested_feature_tags = models.CharField(max_length=255,
                                              blank=True, null=True)
    suggested_cuisine_tags = models.CharField(max_length=255,
                                              blank=True, null=True)
    content = models.TextField("Review")

    def __unicode__(self):
        return "%s -- %s" % (self.vendor.name, str(self.created))

    def get_absolute_url(self):
        return "/vendors/%d-%s/" % (self.vendor.id, slugify(self.vendor.name))

    class Meta:
        get_latest_by = "created"
        ordering = ('created',)
        verbose_name = "Review"
        verbose_name_plural = "Reviews"


class VendorManager(models.GeoManager):
    "Manager class for handling searches by vendor."

    def pending_approval(self):
        """returns all vendors that are not approved, which are
        otherwise impossible to get in a normal query (for now)."""
        normal_qs = super(VendorManager, self).get_query_set()
        pending = normal_qs.filter(approval_status='pending')
        return pending


class ApprovedVendorManager(VendorManager):
    """Manager for approved vendors only.

    Inherits the normal vendor manager."""
    def get_query_set(self):
        normal_qs = super(VendorManager, self).get_query_set()
        new_qs = normal_qs.filter(approval_status='approved')
        return new_qs


class Vendor(models.Model):
    "The main class for this application"

    # CORE FIELDS
    name = models.CharField(max_length=255, unique=True)
    address = models.TextField(null=True)
    neighborhood = models.ForeignKey('Neighborhood', blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True,
                             validators=[validators.validate_phone_number])
    website = models.URLField(blank=True, null=True,
                              validators=[validators.validate_website])
    location = models.PointField(srid=4326, default=None,
                                 null=True, blank=True, editable=False)

    # ADMINISTRATIVE FIELDS
    created = models.DateTimeField(auto_now_add=True, null=True)
    submitted_by = models.ForeignKey(User, null=True, blank=True)
    modified = models.DateTimeField(auto_now=True, null=True)
    approval_status = models.CharField(max_length=100,
                                       default='pending',
                                       choices=(('pending',
                                                 'Pending Approval'),

                                                ('approved',
                                                 'Approved'),

                                                ('quarantined',
                                                 'Quarantined')))
    objects = VendorManager()
    approved_objects = ApprovedVendorManager()

    # DESCRIPTIVE FIELDS
    notes = models.TextField(blank=True, null=True,
                             help_text=("Use this section to briefly describe "
                                        "the vendor. Notes will appear below "
                                        "the vendor's name."))
    veg_level = models.ForeignKey('VegLevel', blank=True, null=True,
                                  help_text=("How vegan friendly is "
                                             "this place? See "
                                             "documentation for "
                                             "guidelines."))

    cuisine_tags = models.ManyToManyField('CuisineTag', null=True, blank=True)
    feature_tags = models.ManyToManyField('FeatureTag', null=True, blank=True)
    vegan_dishes = models.ManyToManyField('VeganDish', null=True, blank=True)

    def needs_geocoding(self, previous_state=None):
        """
        Determine if a vendor needs to be geocoded.

        This method is a little bit complicated for performance reasons.
        It short circuits to False in the case where there is no address,
        True in the case where there is an address and no location.

        Otherwise, it looks at the passed in previous_state, or, when missing,
        queries for the previous state. If the address has changed, geocode
        again.
        """

        # can't EVER geocode without an address
        if not self.address:
            return False

        # if the location is missing, always geocode
        elif not self.location:
            return True

        else:

            # if it's new, and already has an address AND location
            # raise an error, this shouldn't happen.
            if self.pk is None:
                error = "How did this new object already get a location?"
                raise Exception(error)

            else:
                if not previous_state:
                    previous_state = Vendor.objects.get(pk=self.pk)

                if previous_state.address != self.address:
                    needs_geocoding = True
                else:
                    needs_geocoding = False

                return needs_geocoding

    def apply_geocoding(self):

        geocode_result = geocode.geocode_address(self.address)
        latitude, longitude, neighborhood = geocode_result

        if neighborhood:
            neighborhood_obj = None
            try:
                neighborhood_obj = Neighborhood.objects.get(name=neighborhood)
            except:
                pass

            if not neighborhood_obj:
                    neighborhood_obj = Neighborhood()
                    neighborhood_obj.name = neighborhood
                    neighborhood_obj.save()

            self.neighborhood = neighborhood_obj

        self.location = Point(x=longitude, y=latitude, srid=4326)

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.save_new(*args, **kwargs)
        else:
            self.save_existing(*args, **kwargs)

    def save_new(self, *args, **kwargs):
        if self.address:
            self.apply_geocoding()
        super(Vendor, self).save(*args, **kwargs)

    def save_existing(self, *args, **kwargs):
        previous_state = Vendor.objects.get(pk=self.pk)

        self.validate_pending(previous_state)

        if self.needs_geocoding(previous_state):
            self.apply_geocoding()

        super(Vendor, self).save(*args, **kwargs)

        # if the approval_status just changed to "approved" from
        # "pending", email the user who submitted the vendor to
        # let them know their submission has succeeded.
        should_send_email = (previous_state.approval_status == 'pending'
                             and self.approval_status == 'approved'
                             and self.submitted_by
                             and self.submitted_by.email)

        if should_send_email:
            email.send_new_vendor_approval(self)

    def validate_pending(self, orig_vendor):
        """
        If the approval_status has just been changed to "pending"
        from any other value, raise an exception. Once a vendor
        has been something other than pending, it cannot return
        to that state. This is required so that a user only gets
        an approval email ONCE.
        """
        previously_not_pending = (orig_vendor.approval_status != 'pending')
        currently_pending = (self.approval_status == 'pending')

        if previously_not_pending and currently_pending:
            # TODO: make this fail gracefully instead of causing a crashpage
            raise ValidationError("Cannot change a vendor back to pending!")

    def best_vegan_dish(self):
        "Returns the best vegan dish for the vendor"
        dishes = collections.Counter()
        vendor_reviews = Review.approved_objects\
                               .filter(vendor=self,
                                       best_vegan_dish__isnull=False)

        for review in vendor_reviews:
            dishes[review.best_vegan_dish] += 1

        if dishes:
            best_vegan_dish, count = dishes.most_common(1)[0]
            return best_vegan_dish
        else:
            return None

    def food_rating(self):
        reviews = Review.approved_objects.filter(vendor=self)
        food_ratings = [review.food_rating for review in reviews
                        if review.food_rating]
        if food_ratings:
            return sum(food_ratings) / len(food_ratings)
        else:
            return None

    def atmosphere_rating(self):
        "calculates the average rating for a vendor"
        reviews = Review.approved_objects.filter(vendor=self)
        atmosphere_ratings = [review.atmosphere_rating for review in reviews
                              if review.atmosphere_rating]
        if atmosphere_ratings:
            return sum(atmosphere_ratings) / len(atmosphere_ratings)
        else:
            return None

    def get_absolute_url(self):
        return "/vendors/%d-%s/" % (self.id, slugify(self.name))

    def __unicode__(self):
        return self.name

    def approved_reviews(self):
        return Review.approved_objects.filter(vendor=self.id)\
                                      .order_by('-created')

    class Meta:
        get_latest_by = "created"
        ordering = ('name',)
        verbose_name = "Vendor"
        verbose_name_plural = "Vendors"


def validate_vegan_dish(sender, instance, action, model, pk_set, **kwargs):

    pre_clear_message = ('You can not clear vegandish relationships on '
                         'this vendor, because there are reviews for this '
                         'vendor that reference vegan_dish relationships. '
                         '\n'
                         'You may be seeing this message because you tried '
                         'to add/remove a vegan_dish using the admin '
                         'interface. Unfortunately, the admin interface is '
                         'too stupid to add/remove one, it clears the list '
                         'and then adds everything back in.'
                         '\n'
                         'Please have a developer delete this object.')

    pre_remove_message = ('You cannot delete this vendor<->vegan_dish '
                          'relationship because there are reviews for '
                          'this vendor that reference this vegan dish. '
                          'You probably don\'t want to do this anyway. '
                          'If this is a mistake, please have a developer '
                          'delete this object.')

    vendor_has_vegan_dishes = (instance.vegan_dishes.count() > 0)
    vendor_has_vegan_dish_reviews = (instance.review_set
                                     .filter(best_vegan_dish__isnull=False)
                                     .count() > 0)

    if vendor_has_vegan_dishes and vendor_has_vegan_dish_reviews:
        if action == 'pre_clear':
            raise ValidationError(pre_clear_message)

        elif action == 'pre_remove':
            if instance.review_set\
                       .filter(best_vegan_dish__in=pk_set)\
                       .count() > 0:
                raise ValidationError(pre_remove_message)

m2m_changed.connect(validate_vegan_dish, sender=Vendor.vegan_dishes.through)

#######################################
# TAGS
#######################################


class CuisineTag(_TagModel):

    class Meta(_TagModel.Meta):
        verbose_name = "Cuisine Tag"
        verbose_name_plural = "Cuisine Tags"


class FeatureTag(_TagModel):

    class Meta(_TagModel.Meta):
        verbose_name = "Feature Tag"
        verbose_name_plural = "Feature Tags"
