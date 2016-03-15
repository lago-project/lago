#!/usr/bin/env ruby
require 'json'
require 'rest-client'

puts 'Creating User Stories from taiga issutes.. STARTED!'

#Getting taiga's token: 
taiga_username = '<taiga user>'
taiga_password = '<taiga pass>'
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

puts 'Loading Issues from Taiga..'
issues = JSON.parse(
    RestClient.get(
        taiga[:url] + "issues?project=#{taiga[:project_id]}",
        {
            :content_type => :json,
            :Authorization => taiga[:token],
            'x-disable-pagination' => true,
        }
    )
)


puts "NOT WORKING, SEE https://github.com/taigaio/taiga-back/issues/663"


puts "Creating Missing User Stories on Taiga.."
issues.each do |issue|
    if issue['generated_user_stories'] =! [] then
        puts "Skipping issue #{issue['ref']} - #{issue['subject']}, already has user story #{issue['generated_user_stories']}"
        next
    end
    puts issue
    puts issue['generated_user_stories']
    next
    puts "Creating User Story on Taiga with subject: #{issue['subject']}"
    user_story = JSON.parse(
        RestClient.post(
            taiga[:url] + 'userstories',
            {
                :project              => taiga[:project_id],
                :subject              => issue['subject'],
                :generated_from_issue => issue['id'].to_int(),
            }.to_json,
            {
                :content_type  => :json,
                :Authorization => taiga[:token]
            }
        )
    )
    puts "OK! Created user story #{user_story['ref']}"
end
