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
        'login': url,
        'login_linktext': url_linktext,
    }

  @staticmethod
  def nicetime(date):
    return date.strftime('%c')

  @staticmethod
  def renderWithLogin(requestHandler, template_name, template_values):
    # Add login link to our template values.
    template_values = dict(template_values.items() +
                           Helpers.createLoginLink(requestHandler).items())
    # Render response to client.
    requestHandler.response.out.write(
        template.render(
            Helpers.fetchTemplate(template_name),
            template_values))

class Story(db.Model):
  """Models an individual Storybook entry with an author, content, and date."""
  author     = db.UserProperty()
  content    = db.StringProperty(multiline=True)
  date       = db.DateTimeProperty(auto_now_add=True)
  up_vote    = db.IntegerProperty(default=0)
  down_vote  = db.IntegerProperty(default=0)

class Comment(db.Model):
  """Models an individual comment with an author, content, and date."""
  story   = db.ReferenceProperty(Story, collection_name='comments')
  author  = db.UserProperty()
  content = db.StringProperty(multiline=True)
  date    = db.DateTimeProperty(auto_now_add=True)

def storyIdToKey(story_id):
  return Key.from_path('Story',
                       int(story_id),
                       parent=storybook_key())

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
        story.nicetime = Helpers.nicetime(story.date)
        story.id = story.key().id()
        story.comment_url = '/story?' + urllib.urlencode({'story_id': story.id})
        story.upvote_url = '/vote?' + urllib.urlencode({
            'story_id': story.id,
            'upvote': 1, 
            })
        story.downvote_url = '/vote?' + urllib.urlencode({
            'story_id': story.id,
            'upvote': 0, 
            })

    if (shuffle):
      random.shuffle(stories)
    return stories
  
  def fetchStory(self, story_id):
    """Fetches a single story from the DataStore."""
    # Prepare a stories query for the datastore.
    # This tells us what to filter by.
    key = storyIdToKey(story_id)
    stories_query = Story.all().filter('__key__ = ', key)

    # Execute the query on the datastore, telling it how many documents we want. We get a list back.
    stories = stories_query.fetch(1)
    # Grab the first member of the list.
    story = stories[0]

    # Add the nicetime to the story.
    story.nicetime = Helpers.nicetime(story.date)
    story.id = story_id
    return story

class MainPage(BasePage):
  """ Homepage. Takes care of the login link and the list of stories. """
  template_name = 'main.html'
  shuffle = False
  def get(self):
    # Fetch Stories from the datastore.
    stories = self.fetchStories(self.shuffle)

    # Our content.
    template_values = { 'stories': stories }
    # Render our response, including our login link.
    Helpers.renderWithLogin(self, self.template_name, template_values)

class CommentPage(BasePage):
  """ The comment page. """
  template_name = 'comment.html'

  def fetchComments(self, story_id):
    """Fetches comments from the DataStore."""
    story_key = storyIdToKey(story_id)
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
    comments = self.fetchComments(story_id)

    # Our content.
    template_values = {
        'story': story,
        'comments': comments,
    }

    # Render comments to page.
    Helpers.renderWithLogin(self, self.template_name, template_values)

class CommentHandler(webapp.RequestHandler):
  """ Handles comment uploading. :"""
  #TODO: Consider merging this with CommentPage handler.
  def post(self):
    story_id = self.request.get('story_id')
    # Create comment object.
    comment = Comment()
    if users.get_current_user():
      comment.author = users.get_current_user()
    # Fetch content from request.
    comment.content = self.request.get('content')
    # Store our story key to trace the relationship.
    comment.story = storyIdToKey(story_id)
    # Store in datastore.
    comment.put()
    # Redirect back to story & comment page.
    self.redirect('/story?' + urllib.urlencode({'story_id': story_id}))

class VoteHandler(BasePage):
  """ Handles up/downvote uploading."""
  def get(self):
    storybook_name = self.request.get('storybook_name')
    story_id = self.request.get('story_id')
    up_or_down = self.request.get('upvote')

    story = self.fetchStory(story_id)

    # Increment up/down votes.
    if int(up_or_down):
      story.up_vote += 1
    else: 
      story.down_vote += 1

    # Store in datastore.
    story.put()

    # Redirect back to home page.
    self.redirect('/')

class NewPage(MainPage):
  """ The input page. Largely the same as the mainpage, but with a different
      template. """
  template_name = 'input.html'

class RandomPage(MainPage):
  """ Same as MainPage, but shows items in a random order."""
  shuffle = True

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
  ('/vote', VoteHandler),
  ('/new', NewPage),
  ('/random', RandomPage),
  ('/sign', Storybook)
], debug=True)

# If we're the entry point to the program, launch the application.
def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
