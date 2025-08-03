pipeline {
    agent any

    environment {
        DOCKER_BUILDKIT = '1'
        COMPOSE_DOCKER_CLI_BUILD = '1'
    }

    stages {
        stage('Checkout SCM') {
            steps {
                // This checks out your code from GitHub/GitLab/Bitbucket, etc.
                git url: 'https://your-repo-url.git', branch: 'main'
            }
        }

        stage('Clone Repository') {
            steps {
                sh '''
                    echo "Cloning Auto-quiz repo..."
                    rm -rf Auto-quiz
                    git clone https://github.com/your-org/Auto-quiz.git
                '''
            }
        }

        stage('Build and Deploy') {
            steps {
                withCredentials([
                    file(credentialsId: 'gcloud-service-account', variable: 'GCLOUD_JSON'),
                    string(credentialsId: 'GEMINI_API_SUMMARIZER', variable: 'GEMINI_API_KEY')
                ]) {
                    dir('Auto-quiz') {
                        sh '''
                            echo "Injecting Google Cloud credentials"

                            echo "Checking if GCLOUD_JSON is available at: $GCLOUD_JSON"
                            ls -l "$GCLOUD_JSON" || echo "GCLOUD_JSON file not found!"

                            mkdir -p services/speech_to_text
                            cp "$GCLOUD_JSON" services/speech_to_text/gcloud.json
                            chmod 644 services/speech_to_text/gcloud.json

                            echo "Setting Gemini API Key"
                            export GEMINI_API_KEY=$GEMINI_API_KEY

                            echo "Building Docker images"
                            docker-compose build

                            echo "Starting containers"
                            docker-compose up -d
                        '''
                    }
                }
            }
        }

        stage('Post Actions') {
            steps {
                echo 'Post-deployment tasks can be added here (tests, health checks, etc.)'
            }
        }
    }

    post {
        success {
            echo '✅ Build and deployment completed successfully!'
        }
        failure {
            echo '❌ Build or deployment failed. Please check logs.'
        }
    }
}
