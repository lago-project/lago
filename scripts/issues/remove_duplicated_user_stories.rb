#!/usr/bin/env ruby
require 'json'
require 'rest-client'

puts 'Removing duplicated User Stories from taiga... STARTED!'

#Getting taiga's token: 
taiga_username = '<taiga user here>'
taiga_password = '<taiga pass here>'
auth = RestClient.post(
    'https://api.taiga.io/api/v1/auth',
    {
        :type => 'normal',
        :username => taiga_username,
        :password => taiga_password
    }.to_json,
    :content_type => :json,
)
taiga_token = JSON.parse(auth)['auth_token']
puts "Got taiga token #{taiga_token}"

#replace with the taiga project id
taiga_project_id = 114180

#taiga params
taiga = {
    :url => 'https://api.taiga.io/api/v1/',
    :token => "Bearer #{taiga_token}",
    :project_id => taiga_project_id,
}

puts 'Loading User Stories from Taiga..'
user_stories = JSON.parse(
    RestClient.get(
        taiga[:url] + "userstories?project=#{taiga[:project_id]}",
        {
            :content_type => :json,
            :Authorization => taiga[:token],
            'x-disable-pagination' => true,
        }
    )
)


puts "Looking for duplicated user stories"
stories_dict = Hash.new { |h, k| h[k] = [] }
duplicated_stories = []
user_stories.each do |user_story|
    if stories_dict[user_story['generated_from_issue']].length() > 0 then
        duplicated_stories << user_story
    end
    stories_dict[user_story['generated_from_issue']] << user_story
end


duplicated_stories.each do |story|
    puts "Found duplicated story ##{story['ref']} - from issue: #{story['generated_from_issue']}: #{story['subject']}"
    RestClient.delete(
        taiga[:url] + "userstories/#{story['id']}",
        {
            :content_type => :json,
            :Authorization => taiga[:token],
        }
    )
    puts "   Deleted"
end
