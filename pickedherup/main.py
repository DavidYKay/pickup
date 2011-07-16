import cgi
import datetime
import os
import random
import urllib
import wsgiref.handlers

from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext.db import Key
from google.appengine.ext.webapp.util import run_wsgi_app

class Constants:
  TEMPLATE_PATH = 'templates/'
  NUM_STORIES = 10
  NUM_COMMENTS = 10

class Helpers:
  """Helper functions that crop up often."""
  @staticmethod
  def fetchTemplate(name):
    return os.path.join(os.path.dirname(__file__), 'templates/' + name)

  @staticmethod
  def createLoginLink(handler):
    if users.get_current_user():
      url = users.create_logout_url(handler.request.uri)
      url_linktext = 'Logout'
    else:
      url = users.create_login_url(handler.request.uri)
      url_linktext = 'Login'
    return {
        'url': url,
        'url_linktext': url_linktext,
    }

class Story(db.Model):
  """Models an individual Storybook entry with an author, content, and date."""
  author  = db.UserProperty()
  content = db.StringProperty(multiline=True)
  date    = db.DateTimeProperty(auto_now_add=True)

class Comment(db.Model):
  """Models an individual comment with an author, content, and date."""
  story   = db.ReferenceProperty(Story, collection_name='comments')
  author  = db.UserProperty()
  content = db.StringProperty(multiline=True)
  date    = db.DateTimeProperty(auto_now_add=True)

def storybook_key(storybook_name=None):
  """Constructs a datastore key for a Storybook entity with storybook_name."""
  return db.Key.from_path('Storybook', storybook_name or 'default_storybook')

class BasePage(webapp.RequestHandler):
  """Abstract superclass to all pages that display the central feed."""
  def fetchStories(self, shuffle=False):
    """Fetches stories from the DataStore.
      TODO: Pass in different parameters based on different criteria.
    """
    storybook_name = self.request.get('storybook_name')
    stories_query = Story.all().ancestor(
        storybook_key(storybook_name)).order('-date')
    stories = stories_query.fetch(Constants.NUM_STORIES)
    # Add the nicetime to the story.
    for story in stories:
        story.nicetime = story.date.strftime('%c')
        story.id = story.key().id()
        story.comment_url = '/story?' + urllib.urlencode({'story_id': story.id})

    if (shuffle):
      random.shuffle(stories)
    return stories

class MainPage(BasePage):
  """ Homepage. Takes care of the login link and the list of stories. """
  template_name = 'main.html'
  sortParams = False
  def get(self):
    # Fetch Stories from the datastore.
    stories = self.fetchStories(self.sortParams)

    # Our content & login link.
    template_values = dict({
        'stories': stories,
    }.items() + Helpers.createLoginLink(self).items())

    path = Helpers.fetchTemplate(self.template_name)
    # Write our response to the client.
    self.response.out.write(
        # Consisting of our template with our values applied.
        template.render(path, template_values))

class CommentPage(BasePage):
  """ The comment page. """
  template_name = 'comment.html'

  def fetchStory(self, story_id):
    """Fetches a single story from the DataStore."""
    # Prepare a stories query for the datastore.
    # This tells us what to filter by.
    key = Key.from_path('Story',
                        int(story_id),
                        parent=storybook_key()
                        )

    stories_query = Story.all().filter('__key__ = ', key)

    # Execute the query on the datastore, telling it how many documents we want. We get a list back.
    stories = stories_query.fetch(1)
    ## Grab the first member of the list.
    story = stories[0]

    # Add the nicetime to the story.
    story.nicetime = story.date.strftime('%c')
    story.id = story_id
    return story

  def fetchComments(self, story_id):
    """Fetches comments from the DataStore."""
    story_key = Key.from_path('Story',
                        int(story_id),
                        parent=storybook_key()
                        )

    comments_query = Comment.all().filter('story = ', story_key).order('-date')
    comments = comments_query.fetch(Constants.NUM_COMMENTS)
    # Add the nicetime to the comment.
    for comment in comments:
        comment.nicetime = comment.date.strftime('%c')
    return comments

  def get(self):
    story_id = self.request.get('story_id')
    # Fetch comments for our given story.
    story = self.fetchStory(story_id)
    #comments = self.fetchComments(story_id)
    comments = self.fetchComments(story_id)

    # Render comments to page.
    # Our content & login link.
    template_values = dict({
        'story': story,
        'comments': comments,
    }.items() + Helpers.createLoginLink(self).items())

    path = Helpers.fetchTemplate(self.template_name)
    self.response.out.write(
        template.render(path, template_values))

class CommentHandler(webapp.RequestHandler):
  """ Handles comment uploading. :"""
  #TODO: Consider merging this with above handler.
  def post(self):
    story_id = self.request.get('story_id')
    # Create comment object.
    comment = Comment()
    if users.get_current_user():
      comment.author = users.get_current_user()
    # Fetch content from request.
    comment.content = self.request.get('content')
    # TODO: See if this works properly
    comment.story = Key.from_path('Story',
                        int(story_id),
                        parent=storybook_key()
                        )

    # Store in datastore.
    comment.put()
    # Redirect back to story & comment page.
    self.redirect('/story?' + urllib.urlencode({'story_id': story_id}))

class NewPage(MainPage):
  """ The input page. Largely the same as the mainpage, but with a different
      template. """
  template_name = 'input.html'

class RandomPage(MainPage):
  """ Same as MainPage, but shows items in a random order."""
  sortParams = True

class Storybook(webapp.RequestHandler):
  """ Headless POST handler. Redirects back to homepage. """
  def post(self):
    # We set the same parent key on the 'Story' to ensure each story is in
    # the same entity group. Queries across the single entity group will be
    # consistent. However, the write rate to a single entity group should
    # be limited to ~1/second.
    storybook_name = self.request.get('storybook_name')
    story = Story(parent=storybook_key(storybook_name))

    if users.get_current_user():
      story.author = users.get_current_user()

    story.content = self.request.get('content')
    # Store the content.
    story.put()
    # Redirect back to the main page.
    self.redirect('/?' + urllib.urlencode({'storybook_name': storybook_name}))


# Bind routes.
application = webapp.WSGIApplication([
  ('/', MainPage),
  ('/story', CommentPage),
  ('/comment', CommentHandler),
  ('/new', NewPage),
  ('/random', RandomPage),
  ('/sign', Storybook)
], debug=True)

# If we're the entry point to the program, launch the application.
def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
