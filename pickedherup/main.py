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
from google.appengine.ext.webapp.util import run_wsgi_app

class Constants:
  TEMPLATE_PATH = 'templates/'
  NUM_STORIES = 10

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
  ('/new', NewPage),
  ('/random', RandomPage),
  ('/sign', Storybook)
], debug=True)

# If we're the entry point to the program, launch the application.
def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
