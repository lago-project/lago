#!/usr/bin/env ruby
require 'json'
require 'rest-client'
require 'io/console'

puts 'Creating User Stories from taiga issutes.. STARTED!'

#Getting taiga's token: 
print 'Taga username: '
taiga_username = gets.chomp
print 'Taiga pass: '
taiga_password = STDIN.noecho(&:gets).chomp
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
response = RestClient.get(
        taiga[:url] + "issues?project=#{taiga[:project_id]}",
        {
            :content_type => :json,
            :Authorization => taiga[:token],
            'x-disable-pagination' => true,
        }
    )
issues = JSON.parse(
    response
)


puts "Creating Missing User Stories on Taiga.."
issues.each do |issue|
    if issue['generated_user_stories'] != [] then
        puts "Skipping issue #{issue['ref']} - #{issue['subject']}, already has user story #{issue['generated_user_stories']}"
        next
    end
    puts "Got issue #{issue['ref']} - #{issue['subject']}, with user story #{issue['generated_user_stories']}"
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
